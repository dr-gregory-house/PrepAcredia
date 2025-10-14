from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf import FlaskForm
from wtforms import HiddenField
from app.utils.db import get_user_db_connection, get_content_db_connection
from app.utils.decorators import admin_required
from app.utils.user_tracking import get_online_users, get_user_activity_history, get_user_statistics, get_user_performance_metrics
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
    conn = get_user_db_connection()
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
    conn = get_user_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Get user activity history
    activity_history = get_user_activity_history(user_id)
    
    # Get user statistics
    statistics = get_user_statistics(user_id)
    
    # Get user performance metrics
    performance_metrics = get_user_performance_metrics(user_id)
    
    return render_template('admin/user_activity.html',
                         user=user,
                         activity_history=activity_history,
                         statistics=statistics,
                         performance=performance_metrics)

class ToggleUserForm(FlaskForm):
    user_id = HiddenField('user_id')

@admin_bp.route('/user/<int:user_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    form = ToggleUserForm()
    if form.validate_on_submit():
        conn = get_user_db_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if user:
                # Additional security: prevent admins from deactivating themselves
                if user_id == session.get('user_id'):
                    flash('You cannot deactivate your own account', 'error')
                else:
                    # Toggle active status
                    new_status = 0 if user['is_active'] == 1 else 1
                    conn.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
                    conn.commit()
                    flash(f"User {'activated' if new_status == 1 else 'deactivated'} successfully", 'success')
            else:
                flash('User not found', 'error')
        finally:
            conn.close()
    else:
        flash('Invalid form submission', 'error')

    return redirect(url_for('admin.dashboard'))

class ToggleAdminForm(FlaskForm):
    user_id = HiddenField('user_id')

@admin_bp.route('/user/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
def toggle_user_admin(user_id):
    form = ToggleAdminForm()
    if form.validate_on_submit():
        # Enhanced security: prevent admin from removing their own admin status
        if user_id == session.get('user_id'):
            flash('You cannot change your own admin status', 'error')
            return redirect(url_for('admin.dashboard'))

        conn = get_user_db_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if user:
                # Additional security: ensure at least one admin always exists
                if user['role'] == 'admin':
                    # Count other active admins
                    other_admins = conn.execute(
                        'SELECT COUNT(*) as count FROM users WHERE role = "admin" AND is_active = 1 AND id != ?',
                        (user_id,)
                    ).fetchone()
                    if other_admins['count'] == 0:
                        flash('Cannot remove admin status - at least one active admin must exist', 'error')
                        conn.close()
                        return redirect(url_for('admin.dashboard'))

                # Toggle admin status
                new_role = 'user' if user['role'] == 'admin' else 'admin'
                conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
                conn.commit()
                flash(f"User {'promoted to admin' if new_role == 'admin' else 'demoted to regular user'} successfully", 'success')
            else:
                flash('User not found', 'error')
        finally:
            conn.close()
    else:
        flash('Invalid form submission', 'error')

    return redirect(url_for('admin.dashboard'))

class DeleteUserForm(FlaskForm):
    user_id = HiddenField('user_id')

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    form = DeleteUserForm()
    if form.validate_on_submit():
        # Prevent admin from deleting themselves
        if user_id == session.get('user_id'):
            flash('You cannot delete your own account', 'error')
            return redirect(url_for('admin.dashboard'))

        conn = get_user_db_connection()
        try:
            # Check if user exists and is not an admin
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

            if user and user['role'] != 'admin':
                # Additional security: ensure at least one admin exists after deletion
                if user['is_active'] == 1:
                    active_admins = conn.execute(
                        'SELECT COUNT(*) as count FROM users WHERE role = "admin" AND is_active = 1 AND id != ?',
                        (user_id,)
                    ).fetchone()
                    if active_admins['count'] == 0:
                        flash('Cannot delete user - at least one active admin must remain', 'error')
                        conn.close()
                        return redirect(url_for('admin.dashboard'))

                # Delete user's associated data in correct order
                # Delete quiz answers first (foreign key constraint)
                quiz_histories = conn.execute('SELECT id FROM quiz_history WHERE user_id = ?', (user_id,)).fetchall()
                for history in quiz_histories:
                    conn.execute('DELETE FROM quiz_answers WHERE quiz_history_id = ?', (history['id'],))

                # Delete quiz history
                conn.execute('DELETE FROM quiz_history WHERE user_id = ?', (user_id,))

                # Delete spaced repetition data
                conn.execute('DELETE FROM spaced_repetition WHERE user_id = ?', (user_id,))

                # Delete user statistics
                conn.execute('DELETE FROM topic_performance WHERE user_id = ?', (user_id,))
                conn.execute('DELETE FROM user_activity WHERE user_id = ?', (user_id,))
                conn.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
                conn.execute('DELETE FROM user_activity_logs WHERE user_id = ?', (user_id,))

                # Finally delete the user
                conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
                conn.commit()
                flash('User deleted successfully', 'success')
            else:
                flash('Cannot delete user (not found or is admin)', 'error')
        except Exception as e:
            conn.rollback()
            flash(f'Error deleting user: {str(e)}', 'error')
        finally:
            conn.close()
    else:
        flash('Invalid form submission', 'error')

    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/settings')
@admin_required
def settings():
    """System settings page"""
    # Gather stats from respective databases
    user_conn = get_user_db_connection()
    try:
        user_count = user_conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        quiz_count = user_conn.execute('SELECT COUNT(*) as count FROM quiz_history').fetchone()['count']
        sr_count = user_conn.execute('SELECT COUNT(*) as count FROM spaced_repetition').fetchone()['count']
    finally:
        user_conn.close()

    content_conn = get_content_db_connection()
    try:
        question_count = content_conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()['count']
    finally:
        content_conn.close()

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

@admin_bp.route('/incorrect-questions')
@admin_required
def incorrect_questions():
    """Show the top 100 questions that are answered incorrectly most often"""
    user_conn = get_user_db_connection()
    content_conn = get_content_db_connection()
    try:
        # Get question statistics from user database first
        question_stats = user_conn.execute('''
            SELECT
                question_id,
                COUNT(*) AS total_attempts,
                SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS incorrect_count
            FROM quiz_answers
            GROUP BY question_id
            HAVING COUNT(*) >= 5 -- Only include questions with at least 5 attempts
        ''').fetchall()

        # Calculate percentages and sort
        question_stats_with_pct = []
        for stat in question_stats:
            stat_dict = dict(stat)
            total = stat_dict['total_attempts']
            incorrect = stat_dict['incorrect_count']
            stat_dict['incorrect_percentage'] = round((incorrect * 100.0 / total), 2)
            question_stats_with_pct.append(stat_dict)

        # Sort by incorrect_percentage DESC, then by incorrect_count DESC
        question_stats_with_pct.sort(key=lambda x: (-x['incorrect_percentage'], -x['incorrect_count']))

        # Get top 100 question IDs
        top_question_ids = [stat['question_id'] for stat in question_stats_with_pct[:100]]

        # Now get the full question details from content database
        if top_question_ids:
            placeholders = ','.join('?' for _ in top_question_ids)
            top_incorrect_questions = content_conn.execute(f'''
                SELECT id, question_text, correct_answer, rationale
                FROM questions
                WHERE id IN ({placeholders})
            ''', top_question_ids).fetchall()

            # Create a mapping of question_id to stats
            stats_mapping = {stat['question_id']: stat for stat in question_stats_with_pct}

            # Add stats to question results
            for question in top_incorrect_questions:
                question_dict = dict(question)
                stats = stats_mapping.get(question_dict['id'])
                if stats:
                    question_dict['total_attempts'] = stats['total_attempts']
                    question_dict['incorrect_count'] = stats['incorrect_count']
                    question_dict['incorrect_percentage'] = stats['incorrect_percentage']
                question_dict = dict(question_dict)  # Convert back
        else:
            top_incorrect_questions = []
        
        # Convert SQLite Row objects to dictionaries for modification
        result_questions = []
        
        for question in top_incorrect_questions:
            # Convert Row to dictionary
            question_dict = dict(question)
            
            # Get chapters for each question
            chapters = content_conn.execute('''
                SELECT c.name
                FROM chapters c
                JOIN question_chapters qc ON c.id = qc.chapter_id
                WHERE qc.question_id = ?
            ''', (question['id'],)).fetchall()

            question_dict['chapters'] = [chapter['name'] for chapter in chapters]

            # Get the options for each question
            options = content_conn.execute('''
                SELECT option_letter, option_text
                FROM options
                WHERE question_id = ?
                ORDER BY option_letter
            ''', (question['id'],)).fetchall()

            question_dict['options'] = [dict(option) for option in options]

            result_questions.append(question_dict)

        return render_template('admin/incorrect_questions.html',
                             questions=result_questions)
    finally:
        user_conn.close()
        content_conn.close()
