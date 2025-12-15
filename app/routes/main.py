from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from app.utils.db import get_content_db_connection
from app.utils.decorators import login_required
from app.utils.user_tracking import log_user_activity
from app.utils.quiz import generate_quiz_id
import random

main_bp = Blueprint('main', __name__)

@main_bp.route('/', methods=['GET', 'POST'])
def home():
    # Redirect unauthenticated users to login page
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    conn = get_content_db_connection()
    # Fetch specialities with counts, ordered by number of questions descending
    rows = conn.execute('''
        SELECT speciality, COUNT(*) AS question_count
        FROM questions
        WHERE speciality IS NOT NULL AND TRIM(speciality) != ''
        GROUP BY speciality
        ORDER BY question_count DESC
    ''').fetchall()
    conn.close()
    specialities = [{ 'name': row['speciality'], 'question_count': row['question_count'] } for row in rows]
    
    if request.method == 'POST':
        selected_specialities = request.form.getlist('specialities')
        num_questions = int(request.form.get('num_questions', 1))
        if not selected_specialities:
            return render_template('home.html', specialities=specialities, error='Please select at least one speciality.')
        
        undiscovered_only = 'undiscovered_only' in request.form
        
        # Clear any existing quiz state
        if 'quiz_id' in session:
            session.pop('quiz_id', None)
        
        # Generate a unique quiz ID
        quiz_id = generate_quiz_id()
        session['quiz_id'] = quiz_id
        session['selected_specialities'] = selected_specialities
        session['num_questions'] = num_questions
        session['undiscovered_only'] = undiscovered_only
        
        # Log the quiz_start activity here - at quiz creation
        if 'user_id' in session:
            log_user_activity(
                session['user_id'],
                'quiz_start',
                f"Started quiz with {num_questions} questions from {len(selected_specialities)} specialities"
            )
        
        return redirect(url_for('quiz.display_quiz'))
    
    return render_template('home.html', specialities=specialities)

@main_bp.route('/get_tags', methods=['POST'])
def get_tags():
    # Deprecated in speciality-only model
    return jsonify({'tags': {}})