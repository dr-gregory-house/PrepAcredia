from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.utils.db import get_db_connection
from app.utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@admin_required
def dashboard():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    
    return render_template('admin/dashboard.html', users=users)

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