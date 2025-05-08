from datetime import datetime, timedelta
from app.utils.db import get_db_connection
import uuid
from flask import request

def create_user_session(user_id):
    """Create a new session for a user"""
    conn = get_db_connection()
    try:
        session_token = str(uuid.uuid4())
        conn.execute('''
            INSERT INTO user_sessions 
            (user_id, session_token, ip_address, user_agent)
            VALUES (?, ?, ?, ?)
        ''', (user_id, session_token, request.remote_addr, request.user_agent.string))
        conn.commit()
        return session_token
    finally:
        conn.close()

def end_user_session(session_token):
    """End a user session"""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE user_sessions 
            SET is_active = 0 
            WHERE session_token = ?
        ''', (session_token,))
        conn.commit()
    finally:
        conn.close()

def update_user_activity(user_id, session_token):
    """Update user's last activity timestamp"""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE user_sessions 
            SET last_activity = CURRENT_TIMESTAMP 
            WHERE user_id = ? AND session_token = ?
        ''', (user_id, session_token))
        conn.commit()
    finally:
        conn.close()

def log_user_activity(user_id, activity_type, activity_details=None):
    """Log user activity"""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO user_activity_logs 
            (user_id, activity_type, activity_details, ip_address)
            VALUES (?, ?, ?, ?)
        ''', (user_id, activity_type, activity_details, request.remote_addr))
        conn.commit()
    finally:
        conn.close()

def get_online_users(timeout_minutes=5):
    """Get list of currently online users"""
    conn = get_db_connection()
    try:
        timeout = datetime.now() - timedelta(minutes=timeout_minutes)
        users = conn.execute('''
            SELECT DISTINCT u.id, u.username, u.name, u.profile_picture,
                   MAX(s.last_activity) as last_activity
            FROM users u
            JOIN user_sessions s ON u.id = s.user_id
            WHERE s.is_active = 1 
            AND s.last_activity > ?
            GROUP BY u.id
            ORDER BY last_activity DESC
        ''', (timeout,)).fetchall()
        return users
    finally:
        conn.close()

def get_user_activity_history(user_id, limit=50):
    """Get user's recent activity history"""
    conn = get_db_connection()
    try:
        activities = conn.execute('''
            SELECT activity_type, activity_details, timestamp
            FROM user_activity_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        return activities
    finally:
        conn.close()

def get_user_statistics(user_id):
    """Get user's activity statistics"""
    conn = get_db_connection()
    try:
        # Get total login count
        login_count = conn.execute('''
            SELECT COUNT(*) as count
            FROM user_sessions
            WHERE user_id = ?
        ''', (user_id,)).fetchone()['count']

        # Get activity counts by type
        activity_counts = conn.execute('''
            SELECT activity_type, COUNT(*) as count
            FROM user_activity_logs
            WHERE user_id = ?
            GROUP BY activity_type
        ''', (user_id,)).fetchall()

        # Get first and last activity
        time_range = conn.execute('''
            SELECT 
                MIN(timestamp) as first_activity,
                MAX(timestamp) as last_activity
            FROM user_activity_logs
            WHERE user_id = ?
        ''', (user_id,)).fetchone()

        return {
            'login_count': login_count,
            'activity_counts': {row['activity_type']: row['count'] for row in activity_counts},
            'first_activity': time_range['first_activity'],
            'last_activity': time_range['last_activity']
        }
    finally:
        conn.close() 