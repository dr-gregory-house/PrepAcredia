from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from app.utils.db import get_user_db_connection, get_content_db_connection
from app.utils.decorators import login_required, admin_required
from app.utils.spaced_repetition import (
    get_current_schedule, 
    set_review_schedule, 
    FASTER_REVIEW, 
    SLOWER_REVIEW, 
    DEFAULT_REVIEW
)
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin dashboard"""
    conn = get_user_db_connection()
    
    # Get system stats
    user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    # Count questions from content DB
    content_conn = get_content_db_connection()
    question_count = content_conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()['count']
    content_conn.close()
    quiz_count = conn.execute('SELECT COUNT(*) as count FROM quiz_history').fetchone()['count']
    sr_count = conn.execute('SELECT COUNT(*) as count FROM spaced_repetition').fetchone()['count']
    
    # Get recent users
    recent_users = conn.execute(
        'SELECT id, username, email, created_at FROM users ORDER BY created_at DESC LIMIT 5'
    ).fetchall()
    
    conn.close()
    
    return render_template('admin/dashboard.html', 
                          stats={
                              'user_count': user_count,
                              'question_count': question_count,
                              'quiz_count': quiz_count,
                              'sr_count': sr_count
                          },
                          recent_users=recent_users)

@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    """List all users"""
    conn = get_user_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    
    return render_template('admin/user_list.html', users=users)

@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    """System settings page"""
    # Get current spaced repetition settings
    current_schedule = get_current_schedule()
    
    return render_template('admin/settings.html', 
                          current_schedule=current_schedule,
                          json_schedule=json.dumps(current_schedule))

@admin_bp.route('/settings/spaced_repetition', methods=['POST'])
@login_required
@admin_required
def update_spaced_repetition():
    """Update spaced repetition settings"""
    schedule_type = request.form.get('schedule_type', 'default')
    
    # Handle custom intervals if provided
    custom_intervals = None
    if schedule_type == 'custom':
        try:
            custom_intervals = json.loads(request.form.get('custom_intervals', '{}'))
            
            # Convert string keys to integers
            custom_intervals = {int(k): v for k, v in custom_intervals.items()}
            
            # Validate all values are numbers
            for difficulty, intervals in custom_intervals.items():
                custom_intervals[difficulty] = [float(interval) for interval in intervals]
                
        except (json.JSONDecodeError, ValueError, TypeError):
            flash('Invalid custom interval format. Using default schedule.', 'error')
            schedule_type = 'default'
    
    # Update the schedule
    set_review_schedule(schedule_type, custom_intervals)
    
    # Provide feedback
    schedule_descriptions = {
        'default': 'Standard spaced repetition schedule',
        'faster': 'Accelerated review schedule (more frequent reviews)',
        'slower': 'Extended review schedule (less frequent reviews)',
        'custom': 'Custom spaced repetition schedule'
    }
    flash(f'Review schedule updated to: {schedule_descriptions[schedule_type]} for all users', 'success')
    
    return redirect(url_for('admin.settings'))

@admin_bp.route('/settings/spaced_repetition/preview', methods=['POST'])
@login_required
@admin_required
def preview_schedule():
    """Preview a schedule without saving it"""
    schedule_type = request.form.get('schedule_type', 'default')
    
    # Determine which schedule to return
    if schedule_type == 'faster':
        schedule = FASTER_REVIEW
    elif schedule_type == 'slower':
        schedule = SLOWER_REVIEW
    elif schedule_type == 'custom':
        try:
            custom_intervals = json.loads(request.form.get('custom_intervals', '{}'))
            
            # Convert string keys to integers
            custom_intervals = {int(k): v for k, v in custom_intervals.items()}
            
            # Validate all values are numbers
            for difficulty, intervals in custom_intervals.items():
                custom_intervals[difficulty] = [float(interval) for interval in intervals]
                
            schedule = custom_intervals
        except (json.JSONDecodeError, ValueError, TypeError):
            schedule = DEFAULT_REVIEW
    else:
        schedule = DEFAULT_REVIEW
    
    # Calculate total days for each difficulty
    total_days = {}
    for difficulty, intervals in schedule.items():
        total_days[difficulty] = sum(intervals)
    
    return jsonify({
        'schedule': schedule,
        'total_days': total_days
    }) 