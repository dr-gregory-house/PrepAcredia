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
            SELECT activity_type, activity_details, timestamp, ip_address
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

def get_user_performance_metrics(user_id):
    """Get detailed user performance metrics including quiz history and topic performance"""
    conn = get_db_connection()
    try:
        # Get quiz history summary
        quiz_summary = conn.execute('''
            SELECT 
                COUNT(*) as total_quizzes,
                AVG(score * 100.0 / total_questions) as average_score,
                SUM(score) as total_correct,
                SUM(total_questions) as total_questions,
                SUM(time_spent) as total_time_spent,
                MAX(quiz_date) as last_quiz_date
            FROM quiz_history
            WHERE user_id = ?
        ''', (user_id,)).fetchone()
        
        # If no quiz history, create a default structure with zero values
        if quiz_summary and quiz_summary['total_quizzes'] == 0:
            quiz_summary = {
                'total_quizzes': 0,
                'average_score': None,
                'total_correct': 0,
                'total_questions': 0,
                'total_time_spent': 0,
                'last_quiz_date': None
            }
        else:
            # Convert Row to dict for JSON serialization
            quiz_summary = dict(quiz_summary)
        
        # Get recent quiz history
        recent_quizzes_raw = conn.execute('''
            SELECT 
                id,
                quiz_date,
                score,
                total_questions,
                (score * 100.0 / total_questions) as percentage,
                selected_chapters,
                selected_tags,
                time_spent
            FROM quiz_history
            WHERE user_id = ?
            ORDER BY quiz_date DESC
            LIMIT 10
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        recent_quizzes = [dict(quiz) for quiz in recent_quizzes_raw]
        
        # Get topic performance
        topic_perf_raw = conn.execute('''
            SELECT 
                tp.chapter_id,
                c.name as chapter_name,
                tp.correct_count,
                tp.incorrect_count,
                CASE
                    WHEN (tp.correct_count + tp.incorrect_count) = 0 THEN 0
                    ELSE (tp.correct_count * 100.0 / (tp.correct_count + tp.incorrect_count))
                END as accuracy,
                tp.last_updated
            FROM topic_performance tp
            JOIN chapters c ON tp.chapter_id = c.id
            WHERE tp.user_id = ?
            ORDER BY accuracy DESC
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        topic_performance = [dict(topic) for topic in topic_perf_raw]
        
        # Get strongest and weakest topics
        strongest_raw = conn.execute('''
            SELECT 
                c.name as chapter_name,
                tp.correct_count,
                tp.incorrect_count,
                CASE
                    WHEN (tp.correct_count + tp.incorrect_count) = 0 THEN 0
                    ELSE (tp.correct_count * 100.0 / (tp.correct_count + tp.incorrect_count))
                END as accuracy
            FROM topic_performance tp
            JOIN chapters c ON tp.chapter_id = c.id
            WHERE tp.user_id = ? AND (tp.correct_count + tp.incorrect_count) >= 5
            ORDER BY accuracy DESC
            LIMIT 3
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        strongest_topics = [dict(topic) for topic in strongest_raw]
        
        weakest_raw = conn.execute('''
            SELECT 
                c.name as chapter_name,
                tp.correct_count,
                tp.incorrect_count,
                CASE
                    WHEN (tp.correct_count + tp.incorrect_count) = 0 THEN 0
                    ELSE (tp.correct_count * 100.0 / (tp.correct_count + tp.incorrect_count))
                END as accuracy
            FROM topic_performance tp
            JOIN chapters c ON tp.chapter_id = c.id
            WHERE tp.user_id = ? AND (tp.correct_count + tp.incorrect_count) >= 5
            ORDER BY accuracy ASC
            LIMIT 3
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        weakest_topics = [dict(topic) for topic in weakest_raw]
        
        # Get recent incorrect questions for targeted improvement
        incorrect_raw = conn.execute('''
            SELECT 
                q.id,
                q.question_text,
                qa.selected_answer,
                qh.quiz_date
            FROM quiz_answers qa
            JOIN quiz_history qh ON qa.quiz_history_id = qh.id
            JOIN questions q ON qa.question_id = q.id
            WHERE qh.user_id = ? AND qa.is_correct = 0
            ORDER BY qh.quiz_date DESC
            LIMIT 5
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        recent_incorrect = [dict(item) for item in incorrect_raw]
        
        # Performance trend over time (monthly)
        monthly_raw = conn.execute('''
            SELECT 
                strftime('%Y-%m', quiz_date) as month,
                COUNT(*) as quizzes_taken,
                AVG(score * 100.0 / total_questions) as average_score,
                SUM(time_spent) as time_spent
            FROM quiz_history
            WHERE user_id = ?
            GROUP BY month
            ORDER BY month DESC
            LIMIT 6
        ''', (user_id,)).fetchall()
        
        # Convert Row objects to dictionaries
        monthly_trend = [dict(month) for month in monthly_raw]
        
        return {
            'quiz_summary': quiz_summary,
            'recent_quizzes': recent_quizzes,
            'topic_performance': topic_performance,
            'strongest_topics': strongest_topics,
            'weakest_topics': weakest_topics,
            'recent_incorrect': recent_incorrect,
            'monthly_trend': monthly_trend
        }
    finally:
        conn.close() 