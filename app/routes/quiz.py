from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.db import get_content_db_connection, get_user_db_connection
from app.utils.user_tracking import log_user_activity
from app.utils.decorators import login_required
from app.utils.quiz import save_quiz_data, load_quiz_data, delete_quiz_data
from app.utils.spaced_repetition import add_to_spaced_repetition, get_spaced_repetition_questions, mark_question_reviewed
from app.utils.analytics import update_topic_performance, update_user_activity
import random
import sys

# Import global variable for tracking database changes
# This will be shared with app.py
# This needs to be at module level
try:
    from app.app import db_changed
except ImportError:
    # Fallback if not available directly
    db_changed = None

quiz_bp = Blueprint('quiz', __name__, url_prefix='/quiz')

@quiz_bp.route('/', methods=['GET', 'POST'])
@login_required
def display_quiz():
    """Display the current question in a quiz session.
    
    This function handles:
    1. Initializing quiz data if it's the first question
    2. Displaying the current question in the quiz
    3. Handling navigation through the quiz
    
    Note: The actual quiz creation happens in the main.home route, where
    quiz_start activity is logged once per quiz.
    """
    # Check if a quiz is in progress
    # For spaced repetition reviews, selected_specialities may not be set
    is_spaced_repetition = session.get('is_spaced_repetition', False)
    if 'quiz_id' not in session or 'num_questions' not in session:
        flash('Quiz session expired or not found. Please start a new quiz.', 'warning')
        return redirect(url_for('main.home'))
    if not is_spaced_repetition and 'selected_specialities' not in session:
        flash('Quiz configuration incomplete. Please start a new quiz.', 'error')
        return redirect(url_for('main.home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    
    # Initialize quiz data if it doesn't exist
    if quiz_state is None:
        # Get user ID for spaced repetition and analytics
        user_id = session.get('user_id')
        
        # Fetch random questions by selected specialities from content DB
        content_conn = get_content_db_connection()
        placeholders = ','.join('?' for _ in session['selected_specialities'])
        undiscovered_only = session.get('undiscovered_only', False)
        params = session['selected_specialities'].copy()
        
        if undiscovered_only and user_id:
            # Exclude questions the user has already answered, by consulting user DB
            user_conn = get_user_db_connection()
            answered_ids = user_conn.execute('''
                SELECT DISTINCT qa.question_id
                FROM quiz_answers qa
                JOIN quiz_history qh ON qa.quiz_history_id = qh.id
                WHERE qh.user_id = ?
            ''', (user_id,)).fetchall()
            user_conn.close()
            answered_set = {row['question_id'] for row in answered_ids}
            questions = content_conn.execute(
				f'SELECT id, question_text_ru, question_text_en, hint, explanation, speciality FROM questions WHERE speciality IN ({placeholders})',
				params
			).fetchall()
            # Filter client-side due to cross-db limitation
            questions = [q for q in questions if q['id'] not in answered_set]
            # Ensure we have questions after filtering
            if not questions:
                content_conn.close()
                flash('No undiscovered questions found for the selected criteria. Try including discovered questions.', 'warning')
                return redirect(url_for('main.home'))
        else:
            questions = content_conn.execute(
				f'SELECT id, question_text_ru, question_text_en, hint, explanation, speciality FROM questions WHERE speciality IN ({placeholders})',
				params
			).fetchall()
        
        # Check if we found any questions
        if not questions:
            if undiscovered_only:
                flash('No undiscovered questions found for the selected criteria. Try including discovered questions.', 'warning')
            else:
                flash('No questions found for the selected chapters and tags.', 'error')
                content_conn.close()
            return redirect(url_for('main.home'))
        
        # If the user is logged in, get their spaced repetition questions
        sr_questions = []
        if user_id:
            # Get questions due for review based on spaced repetition schedule
            sr_questions = get_spaced_repetition_questions(user_id)
        
        # If num_questions is -1, include all available questions
        if session['num_questions'] == -1:
            # Use all questions, just shuffle them
            questions = random.sample(list(questions), len(questions))
        else:
            # Calculate how many regular questions to include
            reg_question_count = session['num_questions'] - len(sr_questions)
            if reg_question_count < 0:
                # If we have more SR questions than requested, just use the first N
                sr_questions = sr_questions[:session['num_questions']]
                reg_question_count = 0
            
            # Check if we have enough regular questions
            if len(questions) < reg_question_count:
                flash(f'Only {len(questions)} regular questions available for the selected criteria.', 'warning')
                reg_question_count = len(questions)
            
            # Use the specified number of questions
            questions = random.sample(list(questions), reg_question_count)
        
        # Process regular questions with bilingual formatting and correctness via options.is_correct
        quiz_data = []
        for q in questions:
            opts = content_conn.execute('SELECT letter, text_ru, text_en, is_correct FROM options WHERE question_id = ? ORDER BY letter', (q['id'],)).fetchall()
            formatted_options = []
            for o in opts:
                formatted_options.append({
                    'id': o['letter'],
                    'text': f"{o['text_ru'] or ''}\n{o['text_en'] or ''}",
                    'is_correct': bool(o['is_correct'])
                })
            
            quiz_data.append({
				'id': q['id'],
				'text': f"{q['question_text_ru'] or ''}\n{q['question_text_en'] or ''}",
				'hint': q['hint'],
				'explanation': q['explanation'],
				'options': formatted_options,
				'is_review': False  # Regular question, not from spaced repetition
			})
        
        # Add spaced repetition questions if any
        for q in sr_questions:
            # Ensure SR questions have the same structure
            if 'text' not in q and 'question_text' in q:
                q['text'] = q['question_text']
            if 'explanation' not in q and 'rationale' in q:
                q['explanation'] = q['rationale']
                
            # Format options to match the expected structure
            formatted_options = []
            for option in q.get('options', []):
                formatted_options.append({
                    'option_letter': option.get('id', ''),
                    'option_text': option.get('text', ''),
                    'is_correct': option.get('is_correct', False)
                })
                
            if formatted_options:
                q['options'] = formatted_options
                
            quiz_data.append(q)
        
        # Shuffle the combined questions
        random.shuffle(quiz_data)
        content_conn.close()
        
        # Check if we have valid quiz data
        if not quiz_data:
            flash('Could not create a quiz with the selected options.', 'error')
            return redirect(url_for('main.home'))
        
        quiz_state = {
            'quiz_data': quiz_data,
            'current_question': 0,
            'score': 0,
            'user_answers': [],
            'answer_submitted': False
        }
        save_quiz_data(quiz_id, quiz_state)
    
    # Get current quiz state
    quiz_data = quiz_state['quiz_data']
    current = quiz_state['current_question']
    
    # Check if we've reached the end of the quiz
    if current >= len(quiz_data):
        # Save final state for results
        session['score'] = quiz_state['score']
        session['total'] = len(quiz_data)
        session['quiz_data'] = quiz_data
        session['user_answers'] = quiz_state['user_answers']
        return redirect(url_for('quiz.results'))
    
    # Handle answer submission
    if request.method == 'POST' and request.form.get('option') and not quiz_state.get('answer_submitted', False):
        # Redirect to the answer route for processing
        # This code path is likely obsolete since we now have a dedicated answer route
        # We'll keep it commented out in case it's needed for reference
        """
        selected = request.form.get('option')
        correct = quiz_data[current]['correct_answer']
        is_correct = (selected == correct)
        
        # Update score if correct
        if is_correct:
            quiz_state['score'] += 1
            
        # Record user's answer for this question
        user_answers = quiz_state.get('user_answers', [])
        while len(user_answers) <= current:
            user_answers.append(None)  # Fill in any gaps
        
        user_answers[current] = {
            'selected': selected,
            'correct': correct,
            'is_correct': is_correct,
            'rationale': quiz_data[current]['rationale'],
            'question_id': quiz_data[current]['id']
        }
        
        # Handle spaced repetition if user is logged in
        user_id = session.get('user_id')
        if user_id and not is_correct:
            # Add incorrectly answered question to spaced repetition
            add_to_spaced_repetition(user_id, quiz_data[current]['id'])
        elif user_id and is_correct and quiz_data[current].get('is_review', False):
            # Update spaced repetition for correctly answered review question
            mark_question_reviewed(user_id, quiz_data[current]['id'], True)
        
        # Get chapter IDs for this question for analytics
        if user_id:
            conn = get_db_connection()
            chapters = conn.execute(
                'SELECT chapter_id FROM question_chapters WHERE question_id = ?', 
                (quiz_data[current]['id'],)
            ).fetchall()
            conn.close()
            
            # Update performance for each chapter
            for chapter in chapters:
                update_topic_performance(user_id, chapter['chapter_id'], is_correct)
        
        quiz_state['user_answers'] = user_answers
        quiz_state['answer_submitted'] = True  # Mark that this question has been answered
        save_quiz_data(quiz_id, quiz_state)
        
        # Return the same question but with rationale
        return render_template(
            'quiz/question.html',
            quiz={
                'id': quiz_id,
                'title': "Custom Quiz",
                'subject': "Mixed Topics",
                'time_limit': None
            },
            question=quiz_data[current],
            current_question=current+1,  # Display is 1-indexed
            total_questions=len(quiz_data),
            show_answer=True,
            user_answer=selected,
            is_correct=is_correct
        )
        """
        return redirect(url_for('quiz.answer'))
    
    # Normal question display (GET or after moving to next question)
    quiz_state['answer_submitted'] = False  # Reset for new question
    save_quiz_data(quiz_id, quiz_state)
    
    # Add a flag for review questions to show different styling
    is_review = quiz_data[current].get('is_review', False)
    
    # Create a quiz object with basic info for the template
    quiz = {
        'id': quiz_id,
        'title': "Custom Quiz",
        'subject': "Mixed Topics",
        'time_limit': None
    }
    
    return render_template(
        'quiz/question.html',
        quiz=quiz,
        question=quiz_data[current],
        current_question=current+1,  # Display is 1-indexed
        total_questions=len(quiz_data),
        show_answer=False,
        is_review=is_review
    )

@quiz_bp.route('/hint', methods=['POST'])
@login_required
def hint():
    """Log that a hint was shown for a question."""
    user_id = session.get('user_id')
    question_id = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        question_id = data.get('question_id')
    else:
        question_id = request.form.get('question_id')
    try:
        if user_id and question_id:
            log_user_activity(user_id, 'hint_shown', f'Question {question_id}')
    except Exception:
        # Best-effort logging; do not break UX
        pass
    return ('', 204)

@quiz_bp.route('/next', methods=['POST'])
@login_required
def next_question():
    if 'quiz_id' not in session:
        return redirect(url_for('main.home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    if quiz_state is None:
        return redirect(url_for('main.home'))

    # Move to next question only if answer was submitted
    if quiz_state.get('answer_submitted', False):
        quiz_state['current_question'] += 1
        save_quiz_data(quiz_id, quiz_state)
    
    # Check if the quiz is complete and redirect to results
    quiz_data = quiz_state['quiz_data']
    current = quiz_state['current_question']
    if current >= len(quiz_data):
        # Save final state for results
        session['score'] = quiz_state['score']
        session['total'] = len(quiz_data)
        session['quiz_data'] = quiz_data
        session['user_answers'] = quiz_state['user_answers']
        return redirect(url_for('quiz.results'))

    return redirect(url_for('quiz.display_quiz'))

@quiz_bp.route('/results')
@login_required
def results():
    global db_changed  # Access the global variable
    
    # Capture score values at the beginning
    score = session.get('score', 0)
    total = session.get('total', 0)
    quiz_data = session.get('quiz_data', [])
    user_answers = session.get('user_answers', [])
    
    # If quiz_data and user_answers are not in session, check if we have a quiz_id and load data
    if (not quiz_data or not user_answers) and 'quiz_id' in session and session['quiz_id']:
        quiz_id = session['quiz_id']
        quiz_state = load_quiz_data(quiz_id)
        
        if quiz_state:
            # Extract data from quiz_state
            quiz_data = quiz_state.get('quiz_data', [])
            user_answers = quiz_state.get('user_answers', [])
            score = quiz_state.get('score', 0)
            total = len(quiz_data) if quiz_data else 0
            
            # Store in session for template rendering
            session['quiz_data'] = quiz_data
            session['user_answers'] = user_answers
            session['score'] = score
            session['total'] = total
    
    # Calculate actual score based on user answers if available
    if not score and user_answers:
        # Recalculate score from answers
        score = sum(1 for answer in user_answers if answer and answer.get('is_correct', False))
    
    # Ensure we have a valid total
    if not total and quiz_data:
        total = len(quiz_data)
    
    # Zip the data for the template
    zipped_data = list(zip(quiz_data, user_answers)) if quiz_data and user_answers else []
    
    # Make sure we have the right length for user_answers
    if quiz_data and user_answers and len(quiz_data) > len(user_answers):
        # Pad user_answers with None to match quiz_data length
        user_answers.extend([None] * (len(quiz_data) - len(user_answers)))
        zipped_data = list(zip(quiz_data, user_answers))
    
    # If user is logged in, save quiz results to database
    quiz_history_id = None
    if 'user_id' in session and quiz_data and user_answers:
        user_id = session['user_id']
        selected_specialities = ','.join(session.get('selected_specialities', []))
        
        conn = get_user_db_connection()
        
    # Calculate total time spent from all answers safely
    total_time_spent = 0
    if user_answers:
        for answer in user_answers:
            if answer and isinstance(answer, dict) and 'time_spent' in answer:
                try:
                    time_value = answer['time_spent']
                    if time_value is not None:
                        total_time_spent += int(time_value)
                except (ValueError, TypeError):
                    # Skip invalid time values
                    pass
        
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO quiz_history (user_id, score, total_questions, selected_specialities, time_spent)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, score, total, selected_specialities, total_time_spent))
            
            # Get the quiz history ID
            quiz_history_id = cursor.lastrowid
            
            # Save individual answers
            for i, question in enumerate(quiz_data):
                if i < len(user_answers) and user_answers[i]:
                    answer = user_answers[i]
                    conn.execute('''
                        INSERT INTO quiz_answers (quiz_history_id, question_id, selected_letter, is_correct)
                        VALUES (?, ?, ?, ?)
                    ''', (quiz_history_id, question['id'], answer['selected'], 1 if answer['is_correct'] else 0))
            
            conn.commit()
            
            # Explicitly mark database as changed
            if db_changed is not None:
                db_changed = True
                
            # Update activity tracking for analytics
            if total > 0:  # Ensure we don't track quizzes with zero questions
                update_user_activity(user_id, total, score)
                
                # Explicitly mark database as changed again (though update_user_activity already modifies DB)
                if db_changed is not None:
                    db_changed = True
                    
        except Exception as e:
            conn.rollback()
            flash(f"Error saving quiz results: {str(e)}", "error")
        finally:
            conn.close()
    
    # Calculate percentage score
    percentage = (score / total) * 100 if total > 0 else 0
    
    # Prepare questions for display
    questions = []
    for i, (q_data, answer) in enumerate(zipped_data):
        if answer:  # Only include questions that were answered
            question = {
                'id': q_data['id'],
                'text': q_data.get('text', q_data.get('question_text', '')),
                'is_correct': answer['is_correct'],
                'user_answer': answer['selected'],
                'explanation': q_data.get('rationale', q_data.get('explanation', '')),
                'options': []
            }
            
            # Add options
            # Determine the correct answer letter either from question data or by inspecting options
            correct_letter = q_data.get('correct_answer')
            if not correct_letter:
                for _opt in q_data['options']:
                    if _opt.get('is_correct'):
                        correct_letter = _opt.get('id', _opt.get('option_letter', ''))
                        break

            for opt in q_data['options']:
                option = {
                    'id': opt.get('id', opt.get('option_letter', '')),
                    'text': opt.get('text', opt.get('option_text', '')),
                    'is_correct': (opt.get('id', opt.get('option_letter', '')) == correct_letter)
                }
                question['options'].append(option)
                
            questions.append(question)
    
    # Create a quiz object with basic info needed by the template
    quiz = {
        'id': quiz_history_id or session.get('quiz_id'),
        'title': "Quiz Results",
        'subject': "Custom Quiz",
        'time_limit': None
    }
    
    # Areas to improve (for lower scores)
    improvement_areas = []
    if percentage < 70:
        improvement_areas = [
            "Focus on reviewing the questions you got wrong",
            "Try taking more practice quizzes on similar topics",
            "Consider reviewing the related study materials"
        ]
    
    # Prepare template rendering with captured data
    result_data = {
        'quiz': quiz,
        'score': score,
        'total_questions': total,
        'percentage': percentage,
        'questions': questions,
        'time_spent': sum(answer.get('time_spent', 0) for answer in user_answers if answer) if user_answers else 0,
        'improvement_areas': improvement_areas
    }
    
    # Clean up session and temp data
    if 'quiz_id' in session and session['quiz_id']:
        delete_quiz_data(session['quiz_id'])
        # Remove quiz_id from session but keep the key with None value
        # This helps the navbar to know we're not in a quiz anymore
        session['quiz_id'] = None
    
    # Keep user session data, but clear quiz-related data
    keys_to_remove = ['selected_chapters', 'selected_tags', 'num_questions', 'score', 'total', 'quiz_data', 'user_answers', 'selected_specialities']
    for key in keys_to_remove:
        if key in session:
            session.pop(key)
    
    # Check if this was a spaced repetition review and all questions are now completed
    if session.get('is_spaced_repetition') and percentage > 0:
        # Clear this flag
        session.pop('is_spaced_repetition', None)
        
        # Return a special congratulations template
        return render_template('quiz/review_complete.html', 
                              score=score, 
                              total_questions=total, 
                              percentage=percentage)
    
    # Return the template with the captured data
    return render_template('quiz/results.html', **result_data)

@quiz_bp.route('/exit', methods=['POST', 'GET'])
@login_required
def exit_quiz():
    """Handle quiz exit - clean up session data and redirect to home."""
    if 'quiz_id' not in session:
        flash('No active quiz session found.', 'info')
        return redirect(url_for('main.home'))

    quiz_id = session['quiz_id']

    # Log the exit activity if user is logged in
    user_id = session.get('user_id')
    if user_id:
        try:
            log_user_activity(user_id, 'quiz_exited', f'Quiz {quiz_id} exited early')
        except Exception:
            # Best-effort logging; don't break UX
            pass

    # Clean up quiz data
    try:
        delete_quiz_data(quiz_id)
    except Exception:
        # Best-effort cleanup; don't break UX
        pass

    # Clear quiz-related session data
    keys_to_remove = [
        'quiz_id', 'selected_chapters', 'selected_tags', 'num_questions',
        'score', 'total', 'quiz_data', 'user_answers', 'selected_specialities',
        'is_spaced_repetition', 'undiscovered_only'
    ]

    for key in keys_to_remove:
        if key in session:
            session.pop(key)

    flash('Quiz exited successfully. Progress has been cleared.', 'info')
    return redirect(url_for('main.home'))

@quiz_bp.route('/answer', methods=['POST'])
@login_required
def answer():
    global db_changed  # Access the global variable
    
    if 'quiz_id' not in session:
        return redirect(url_for('main.home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    if quiz_state is None:
        flash('Quiz session expired', 'error')
        return redirect(url_for('main.home'))
    
    # Get current question data
    current = quiz_state['current_question']
    quiz_data = quiz_state['quiz_data']
    
    if current >= len(quiz_data):
        return redirect(url_for('quiz.results'))
    
    # Get selected answer and question ID
    selected = request.form.get('answer')
    question_id = request.form.get('question_id')
    time_spent = request.form.get('time_spent', 0)

    # Validate input parameters
    if not selected:
        flash('Please select an answer.', 'error')
        return redirect(url_for('quiz.display_quiz'))
    if not question_id:
        flash('Question ID is missing. Please try again.', 'error')
        return redirect(url_for('quiz.display_quiz'))
    
    # Verify question ID matches current question
    if str(quiz_data[current]['id']) != str(question_id):
        flash('Question ID mismatch, please try again', 'error')
        return redirect(url_for('quiz.display_quiz'))
    
    # Process the answer
    current_question = quiz_data[current]
    # Determine correctness from options
    is_correct = False
    # Determine the correct option letter for the current question
    correct = None
    for opt in current_question['options']:
        if str(opt.get('id')) == str(selected) and opt.get('is_correct'):
            is_correct = True
            break
        if opt.get('is_correct'):
            # Capture the correct answer letter
            correct = str(opt.get('id'))
    
    # Update score if correct
    if is_correct:
        quiz_state['score'] += 1
    
    # Record user's answer for this question
    user_answers = quiz_state.get('user_answers', [])
    while len(user_answers) <= current:
        user_answers.append(None)  # Fill in any gaps
    
    user_answers[current] = {
        'selected': selected,
        'correct': correct,
        'is_correct': is_correct,
        'rationale': current_question.get('rationale') or current_question.get('explanation', ''),
        'question_id': current_question['id'],
        'time_spent': int(time_spent) if time_spent else 0,
        'hint_used': request.form.get('hint_used', '0') == '1'
    }
    
    # Handle spaced repetition if user is logged in
    user_id = session.get('user_id')
    if user_id and not is_correct:
        # Add incorrectly answered question to spaced repetition
        add_to_spaced_repetition(user_id, quiz_data[current]['id'])
        
        # Explicitly mark database as changed
        if db_changed is not None:
            db_changed = True
    elif user_id and is_correct and quiz_data[current].get('is_review', False):
        # Update spaced repetition for correctly answered review question
        mark_question_reviewed(user_id, quiz_data[current]['id'], True)
        
        # Explicitly mark database as changed
        if db_changed is not None:
            db_changed = True
    
    # Get chapter IDs for this question for analytics
    # Update performance by speciality
    if user_id:
        # Fetch speciality for the current question
        content_conn = get_content_db_connection()
        row = content_conn.execute('SELECT speciality FROM questions WHERE id = ?', (quiz_data[current]['id'],)).fetchone()
        content_conn.close()
        speciality = row['speciality'] if row else None
        if speciality:
            update_topic_performance(user_id, speciality, is_correct)
            
            # Explicitly mark database as changed
            if db_changed is not None:
                db_changed = True
    
    quiz_state['user_answers'] = user_answers
    quiz_state['answer_submitted'] = True  # Mark that this question has been answered
    save_quiz_data(quiz_id, quiz_state)
    
    # Return the same question but with feedback
    return render_template(
        'quiz/question.html',
        quiz={
            'id': quiz_id,
            'title': "Custom Quiz",
            'subject': "Mixed Topics",
            'time_limit': None
        },
        question=quiz_data[current],
        current_question=current+1,  # Display is 1-indexed
        total_questions=len(quiz_data),
        show_answer=True,
        user_answer=selected,
        is_correct=is_correct,
        next_question_url=url_for('quiz.next_question')
    )
