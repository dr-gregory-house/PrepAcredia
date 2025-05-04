from flask import Blueprint, render_template, session, flash, redirect, url_for, jsonify, request
from app.utils.db import get_db_connection
from app.utils.decorators import login_required
from app.utils.analytics import get_topic_performance, get_activity_heatmap, get_learning_progress, get_user_stats_summary
from app.utils.spaced_repetition import get_spaced_repetition_questions, mark_question_reviewed, set_review_schedule, get_current_schedule
from app.utils.quiz import generate_quiz_id, save_quiz_data
import json
import uuid

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

@profile_bp.route('/')
@login_required
def profile():
    user_id = session['user_id']
    conn = get_db_connection()
    
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    quiz_history = conn.execute('''
        SELECT * FROM quiz_history 
        WHERE user_id = ? 
        ORDER BY quiz_date DESC
    ''', (user_id,)).fetchall()
    
    # Format history data
    history_data = []
    for quiz in quiz_history:
        history_data.append({
            'id': quiz['id'],
            'date': quiz['quiz_date'],
            'score': quiz['score'],
            'total': quiz['total_questions'],
            'percentage': (quiz['score'] / quiz['total_questions']) * 100 if quiz['total_questions'] > 0 else 0
        })
    
    conn.close()
    
    return render_template('profile/profile.html', user=user, history=history_data)

@profile_bp.route('/analytics')
@login_required
def analytics():
    user_id = session['user_id']
    
    # Get user's overall stats
    stats = get_user_stats_summary(user_id)
    
    # Get topic performance data
    topic_performance = get_topic_performance(user_id)
    
    # Get learning progress data (last 90 days)
    progress_data = get_learning_progress(user_id)
    
    # Get activity heatmap data
    heatmap_data = get_activity_heatmap(user_id)
    
    # Get spaced repetition count
    sr_questions = get_spaced_repetition_questions(user_id, count=100)  # Get up to 100 for counting
    sr_due_count = len(sr_questions)
    
    # Get current review schedule information
    review_schedule = get_current_schedule()
    
    # Convert data to JSON for JavaScript charts
    json_topic_data = json.dumps(topic_performance)
    json_progress_data = json.dumps(progress_data)
    json_heatmap_data = json.dumps(heatmap_data)
    json_review_schedule = json.dumps(review_schedule)
    
    return render_template('profile/analytics.html', 
                          stats=stats,
                          topic_performance=topic_performance,
                          json_topic_data=json_topic_data,
                          json_progress_data=json_progress_data,
                          json_heatmap_data=json_heatmap_data,
                          json_review_schedule=json_review_schedule,
                          sr_due_count=sr_due_count)

@profile_bp.route('/quiz/<int:quiz_id>')
@login_required
def quiz_detail(quiz_id):
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Get quiz and verify it belongs to the user
    quiz = conn.execute('''
        SELECT * FROM quiz_history WHERE id = ? AND user_id = ?
    ''', (quiz_id, user_id)).fetchone()
    
    if not quiz:
        conn.close()
        flash('Quiz not found', 'error')
        return redirect(url_for('profile.profile'))
    
    # Get quiz answers
    answers = conn.execute('''
        SELECT qa.*, q.question_text, q.correct_answer, q.rationale
        FROM quiz_answers qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.quiz_history_id = ?
    ''', (quiz_id,)).fetchall()
    
    # Get options for each question
    questions_with_options = []
    for answer in answers:
        options = conn.execute('''
            SELECT option_letter, option_text 
            FROM options 
            WHERE question_id = ? 
            ORDER BY option_letter
        ''', (answer['question_id'],)).fetchall()
        
        questions_with_options.append({
            'question_id': answer['question_id'],
            'question_text': answer['question_text'],
            'selected_answer': answer['selected_answer'],
            'correct_answer': answer['correct_answer'],
            'is_correct': answer['is_correct'],
            'rationale': answer['rationale'],
            'options': [dict(option) for option in options]
        })
    
    conn.close()
    
    return render_template('profile/quiz_detail.html', 
                          quiz=quiz, 
                          questions=questions_with_options)

@profile_bp.route('/review', methods=['GET'])
@login_required
def spaced_repetition_review():
    """
    Dedicated page for spaced repetition review
    """
    user_id = session['user_id']
    
    # Get questions due for review
    sr_questions = get_spaced_repetition_questions(user_id, count=50)  # Get up to 50 for review
    sr_due_count = len(sr_questions)
    
    if sr_due_count == 0:
        flash('You have no cards due for review. Great job staying on top of your studies!', 'info')
        return redirect(url_for('profile.profile'))
    
    # Create a special quiz session with only spaced repetition questions
    quiz_id = generate_quiz_id()
    
    # Save quiz state with only review questions
    quiz_state = {
        'quiz_data': sr_questions,
        'current_question': 0,
        'score': 0,
        'user_answers': [],
        'answer_submitted': False,
        'is_spaced_repetition': True  # Mark as a spaced repetition session
    }
    save_quiz_data(quiz_id, quiz_state)
    
    # Set session variables
    session['quiz_id'] = quiz_id
    session['selected_chapters'] = []  # Empty as this is a review session
    session['selected_tags'] = []  # Empty as this is a review session
    session['num_questions'] = sr_due_count
    session['is_spaced_repetition'] = True  # Mark this as a spaced repetition session
    
    # Redirect to the quiz route which will handle the questions
    return redirect(url_for('quiz.start_quiz'))

@profile_bp.route('/review_status')
@login_required
def review_status():
    """
    Simple AJAX endpoint to get spaced repetition status for display in the navbar
    """
    user_id = session['user_id']
    sr_questions = get_spaced_repetition_questions(user_id, count=100)
    sr_due_count = len(sr_questions)
    
    return jsonify({
        'count': sr_due_count,
        'has_due': sr_due_count > 0
    })

@profile_bp.route('/set_review_schedule', methods=['POST'])
@login_required
def change_review_schedule():
    """
    Change the spaced repetition review schedule
    """
    schedule_type = request.form.get('schedule_type', 'default')
    
    # Validate schedule type
    if schedule_type not in ['default', 'faster', 'slower']:
        flash('Invalid schedule type. Using default schedule.', 'warning')
        schedule_type = 'default'
    
    # Set the new schedule
    set_review_schedule(schedule_type)
    
    # Display confirmation message
    schedule_descriptions = {
        'default': 'Standard spaced repetition schedule',
        'faster': 'Accelerated review schedule (more frequent reviews)',
        'slower': 'Extended review schedule (less frequent reviews)'
    }
    flash(f'Review schedule updated to: {schedule_descriptions[schedule_type]}', 'success')
    
    # Redirect back to analytics page
    return redirect(url_for('profile.analytics')) 