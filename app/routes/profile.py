from flask import Blueprint, render_template, session, flash, redirect, url_for
from app.utils.db import get_db_connection
from app.utils.decorators import login_required

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