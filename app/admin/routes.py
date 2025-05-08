from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.utils.db import get_db_connection
from app.utils.decorators import admin_required
from app.utils.user_tracking import get_online_users, get_user_activity_history, get_user_statistics
from app.utils.spaced_repetition import (
    get_current_schedule, 
    set_review_schedule, 
    FASTER_REVIEW, 
    SLOWER_REVIEW, 
    DEFAULT_REVIEW,
    save_schedule_preset,
    get_schedule_presets,
    delete_schedule_preset
)
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@admin_required
def dashboard():
    conn = get_db_connection()
    try:
        # Get all users
        users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        
        # Get online users
        online_users = get_online_users()
        
        # Get recent activity logs for all users
        recent_activities = conn.execute('''
            SELECT l.*, u.username, u.name
            FROM user_activity_logs l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.timestamp DESC
            LIMIT 50
        ''').fetchall()
        
        return render_template('admin/dashboard.html', 
                            users=users,
                            online_users=online_users,
                            recent_activities=recent_activities)
    finally:
        conn.close()

@admin_bp.route('/user/<int:user_id>/activity')
@admin_required
def user_activity(user_id):
    # Get user details
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Get user activity history
    activity_history = get_user_activity_history(user_id)
    
    # Get user statistics
    statistics = get_user_statistics(user_id)
    
    return render_template('admin/user_activity.html',
                         user=user,
                         activity_history=activity_history,
                         statistics=statistics)

@admin_bp.route('/user/<int:user_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user:
        # Toggle active status
        new_status = 0 if user['is_active'] == 1 else 1
        conn.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
        conn.commit()
        flash(f"User {'activated' if new_status == 1 else 'deactivated'} successfully", 'success')
    else:
        flash('User not found', 'error')
    
    conn.close()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/user/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def toggle_user_admin(user_id):
    # Don't allow admin to remove their own admin status
    if user_id == session.get('user_id'):
        flash('You cannot change your own admin status', 'error')
        return redirect(url_for('admin.dashboard'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user:
        # Toggle admin status
        new_role = 'user' if user['role'] == 'admin' else 'admin'
        conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
        conn.commit()
        flash(f"User {'promoted to admin' if new_role == 'admin' else 'demoted to regular user'} successfully", 'success')
    else:
        flash('User not found', 'error')
    
    conn.close()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    conn = get_db_connection()
    # Check if user exists and is not an admin
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user and user['role'] != 'admin':
        # Delete user's quiz history and answers
        quiz_histories = conn.execute('SELECT id FROM quiz_history WHERE user_id = ?', (user_id,)).fetchall()
        for history in quiz_histories:
            conn.execute('DELETE FROM quiz_answers WHERE quiz_history_id = ?', (history['id'],))
        
        conn.execute('DELETE FROM quiz_history WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        flash('User deleted successfully', 'success')
    else:
        flash('Cannot delete user (not found or is admin)', 'error')
    
    conn.close()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/settings')
@admin_required
def settings():
    """System settings page"""
    conn = get_db_connection()
    
    # Get system stats for the dashboard
    user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    question_count = conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()['count']
    quiz_count = conn.execute('SELECT COUNT(*) as count FROM quiz_history').fetchone()['count']
    sr_count = conn.execute('SELECT COUNT(*) as count FROM spaced_repetition').fetchone()['count']
    
    conn.close()
    
    # Get current spaced repetition settings
    current_schedule = get_current_schedule()
    
    # Get saved schedule presets
    schedule_presets = get_schedule_presets()
    
    return render_template('admin/settings.html', 
                          current_schedule=current_schedule,
                          json_schedule=json.dumps(current_schedule),
                          schedule_presets=schedule_presets,
                          json_presets=json.dumps(schedule_presets),
                          stats={
                              'user_count': user_count,
                              'question_count': question_count,
                              'quiz_count': quiz_count,
                              'sr_count': sr_count
                          })

@admin_bp.route('/settings/spaced_repetition', methods=['POST'])
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
    
    # Save as preset if requested
    preset_name = request.form.get('save_preset_name', '').strip()
    if preset_name and schedule_type == 'custom' and custom_intervals:
        save_schedule_preset(preset_name, custom_intervals)
        flash(f'Schedule preset "{preset_name}" saved successfully', 'success')
    
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

@admin_bp.route('/settings/preset/<preset_name>', methods=['GET'])
@admin_required
def get_preset(preset_name):
    """Get a saved schedule preset"""
    presets = get_schedule_presets()
    if preset_name in presets:
        return jsonify({
            'success': True,
            'preset': presets[preset_name]
        })
    return jsonify({
        'success': False,
        'error': 'Preset not found'
    }), 404

@admin_bp.route('/settings/preset/<preset_name>', methods=['DELETE'])
@admin_required
def remove_preset(preset_name):
    """Delete a saved schedule preset"""
    if delete_schedule_preset(preset_name):
        return jsonify({
            'success': True,
            'message': f'Preset "{preset_name}" deleted successfully'
        })
    return jsonify({
        'success': False,
        'error': 'Failed to delete preset'
    }), 500

@admin_bp.route('/settings/spaced_repetition/preview', methods=['POST'])
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