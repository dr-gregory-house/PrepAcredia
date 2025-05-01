from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.db import get_db_connection
from app.utils.decorators import login_required
from app.utils.quiz import save_quiz_data, load_quiz_data, delete_quiz_data
import random

quiz_bp = Blueprint('quiz', __name__, url_prefix='/quiz')

@quiz_bp.route('/', methods=['GET', 'POST'])
@login_required
def start_quiz():
    # Check if a quiz is in progress
    if 'quiz_id' not in session or 'selected_chapters' not in session or 'num_questions' not in session:
        return redirect(url_for('main.home'))
    
    quiz_id = session['quiz_id']
    quiz_state = load_quiz_data(quiz_id)
    
    # Initialize quiz data if it doesn't exist
    if quiz_state is None:
        # Fetch random questions from selected chapters and tags
        conn = get_db_connection()
        chapter_ids = ','.join('?' for _ in session['selected_chapters'])
        tag_ids = ','.join('?' for _ in session['selected_tags']) if session['selected_tags'] else None
        
        if tag_ids:
            query = f"""
                SELECT DISTINCT q.id, q.question_text, q.correct_answer, q.rationale FROM questions q
                JOIN question_chapters qc ON q.id = qc.question_id
                JOIN question_tags qt ON q.id = qt.question_id
                WHERE qc.chapter_id IN ({chapter_ids}) AND qt.tag_id IN ({tag_ids})
            """
            params = session['selected_chapters'] + session['selected_tags']
        else:
            query = f"""
                SELECT DISTINCT q.id, q.question_text, q.correct_answer, q.rationale FROM questions q
                JOIN question_chapters qc ON q.id = qc.question_id
                WHERE qc.chapter_id IN ({chapter_ids})
            """
            params = session['selected_chapters']
        
        questions = conn.execute(query, params).fetchall()
        
        # If num_questions is -1, include all available questions
        if session['num_questions'] == -1:
            # Use all questions, just shuffle them
            questions = random.sample(list(questions), len(questions))
        else:
            # Use the specified number of questions
            questions = random.sample(list(questions), min(session['num_questions'], len(questions)))
        
        quiz_data = []
        for q in questions:
            options = conn.execute('SELECT option_letter, option_text FROM options WHERE question_id = ? ORDER BY option_letter', (q['id'],)).fetchall()
            quiz_data.append({
                'id': q['id'],
                'question_text': q['question_text'],
                'correct_answer': q['correct_answer'],
                'rationale': q['rationale'],
                'options': [dict(option) for option in options]
            })
        conn.close()
        
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
            'rationale': quiz_data[current]['rationale']
        }
        
        quiz_state['user_answers'] = user_answers
        quiz_state['answer_submitted'] = True  # Mark that this question has been answered
        save_quiz_data(quiz_id, quiz_state)
        
        # Return the same question but with rationale
        return render_template(
            'quiz/question.html',
            question=quiz_data[current],
            current=current+1,  # Display is 1-indexed
            total=len(quiz_data),
            show_rationale=True,
            current_answer=user_answers[current]  # Pass specific answer for this question
        )
    
    # Normal question display (GET or after moving to next question)
    quiz_state['answer_submitted'] = False  # Reset for new question
    save_quiz_data(quiz_id, quiz_state)
    return render_template(
        'quiz/question.html',
        question=quiz_data[current],
        current=current+1,  # Display is 1-indexed
        total=len(quiz_data),
        show_rationale=False
    )

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

    return redirect(url_for('quiz.start_quiz'))

@quiz_bp.route('/results')
@login_required
def results():
    score = session.get('score', 0)
    total = session.get('total', 0)
    quiz_data = session.get('quiz_data', [])
    user_answers = session.get('user_answers', [])
    
    # Zip the data for the template
    zipped_data = list(zip(quiz_data, user_answers)) if quiz_data and user_answers else []
    
    # If user is logged in, save quiz results to database
    if 'user_id' in session and quiz_data and user_answers:
        user_id = session['user_id']
        selected_chapters = ','.join(session.get('selected_chapters', []))
        selected_tags = ','.join(session.get('selected_tags', [])) if session.get('selected_tags') else None
        
        conn = get_db_connection()
        
        # Create quiz history record
        cursor = conn.execute('''
            INSERT INTO quiz_history (user_id, score, total_questions, selected_chapters, selected_tags)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, score, total, selected_chapters, selected_tags))
        
        # Get the quiz history ID
        quiz_history_id = cursor.lastrowid
        
        # Save individual answers
        for i, question in enumerate(quiz_data):
            if i < len(user_answers) and user_answers[i]:
                answer = user_answers[i]
                conn.execute('''
                    INSERT INTO quiz_answers (quiz_history_id, question_id, selected_answer, is_correct)
                    VALUES (?, ?, ?, ?)
                ''', (quiz_history_id, question['id'], answer['selected'], 1 if answer['is_correct'] else 0))
        
        conn.commit()
        conn.close()
    
    # Clean up session and temp data
    if 'quiz_id' in session:
        delete_quiz_data(session['quiz_id'])
    
    # Keep user session data, but clear quiz-related data
    session_keys_to_keep = ['user_id', 'user_name', 'user_role', 'google_token']
    session_copy = {k: session[k] for k in session_keys_to_keep if k in session}
    session.clear()
    
    # Restore user session data
    for key, value in session_copy.items():
        session[key] = value
    
    return render_template('quiz/results.html', score=score, total=total, zipped_data=zipped_data) 