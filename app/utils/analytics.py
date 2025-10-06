from datetime import datetime, timedelta
from app.utils.db import get_user_db_connection
import json

def update_topic_performance(user_id, speciality, is_correct):
    """
    Update user performance stats for a specific topic/chapter
    """
    conn = get_user_db_connection()
    try:
        # Check if we already have a record for this user and chapter
        existing = conn.execute(
            'SELECT id, correct_count, incorrect_count FROM topic_performance WHERE user_id = ? AND speciality = ?',
            (user_id, speciality)
        ).fetchone()
        
        now = datetime.now()
        
        if existing:
            # Update existing record
            correct_count = existing['correct_count'] + (1 if is_correct else 0)
            incorrect_count = existing['incorrect_count'] + (0 if is_correct else 1)
            
            conn.execute('UPDATE topic_performance SET correct_count = ?, incorrect_count = ?, last_updated = ? WHERE id = ?', (correct_count, incorrect_count, now, existing['id']))
        else:
            # Insert new record
            conn.execute('INSERT INTO topic_performance (user_id, speciality, correct_count, incorrect_count, last_updated) VALUES (?, ?, ?, ?, ?)', (user_id, speciality, 1 if is_correct else 0, 0 if is_correct else 1, now))
        
        conn.commit()
    finally:
        conn.close()

def update_user_activity(user_id, questions_count, correct_count):
    """
    Update daily activity tracking for heatmap visualization
    """
    # Safety check to prevent zero division errors
    if questions_count <= 0:
        questions_count = 1  # Ensure at least 1 question
    
    conn = get_user_db_connection()
    try:
        today = datetime.now().date()
        
        # Check if we already have a record for today
        existing = conn.execute(
            'SELECT id, quiz_count, question_count, correct_count FROM user_activity WHERE user_id = ? AND activity_date = ?',
            (user_id, today)
        ).fetchone()
        
        if existing:
            # Update existing record
            new_quiz_count = existing['quiz_count'] + 1
            new_question_count = existing['question_count'] + questions_count
            new_correct_count = existing['correct_count'] + correct_count
            
            conn.execute(
                '''UPDATE user_activity 
                   SET quiz_count = ?, question_count = ?, correct_count = ?
                   WHERE id = ?''',
                (new_quiz_count, new_question_count, new_correct_count, existing['id'])
            )
        else:
            # Insert new record
            conn.execute(
                '''INSERT INTO user_activity 
                   (user_id, activity_date, quiz_count, question_count, correct_count)
                   VALUES (?, ?, ?, ?, ?)''',
                (user_id, today, 1, questions_count, correct_count)
            )
        
        conn.commit()
    finally:
        conn.close()

def get_topic_performance(user_id):
    """
    Get user performance by topic for the analytics dashboard
    """
    conn = get_user_db_connection()
    try:
        performance_data = conn.execute('SELECT speciality, correct_count, incorrect_count FROM topic_performance WHERE user_id = ? ORDER BY speciality', (user_id,)).fetchall()
        
        # Calculate percentages and format data
        result = []
        for data in performance_data:
            total = data['correct_count'] + data['incorrect_count']
            accuracy = (data['correct_count'] / total * 100) if total > 0 else 0
            
            result.append({
                'topic_id': data['speciality'],
                'topic_name': data['speciality'],
                'correct': data['correct_count'],
                'incorrect': data['incorrect_count'],
                'total': total,
                'accuracy': round(accuracy, 1)
            })
        
        return result
    finally:
        conn.close()

def get_activity_heatmap(user_id, days=365):
    """
    Get user activity data for heatmap visualization
    """
    conn = get_user_db_connection()
    try:
        # Get activity for the last X days
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        activity_data = conn.execute(
            '''SELECT activity_date, quiz_count, question_count, correct_count
               FROM user_activity
               WHERE user_id = ? AND activity_date BETWEEN ? AND ?
               ORDER BY activity_date''',
            (user_id, start_date, end_date)
        ).fetchall()
        
        # Format for heatmap (date: value pairs)
        heatmap_data = {}
        
        # First create a dictionary with all dates in the range (to avoid gaps)
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            heatmap_data[date_str] = 0
            current_date += timedelta(days=1)
        
        # Then fill in actual activity data
        for data in activity_data:
            date_str = data['activity_date']
            # Use question count as the intensity value
            heatmap_data[date_str] = data['question_count']
        
        return heatmap_data
    finally:
        conn.close()

def get_learning_progress(user_id, days=90):
    """
    Get learning progress data over time for charts
    """
    conn = get_user_db_connection()
    try:
        # Get daily performance for trend analysis
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        daily_data = conn.execute(
            '''SELECT activity_date, question_count, correct_count
               FROM user_activity
               WHERE user_id = ? AND activity_date BETWEEN ? AND ?
               ORDER BY activity_date''',
            (user_id, start_date, end_date)
        ).fetchall()
        
        # Calculate cumulative and moving average accuracy
        result = []
        cumulative_questions = 0
        cumulative_correct = 0
        
        for data in daily_data:
            date_str = data['activity_date']
            daily_questions = data['question_count']
            daily_correct = data['correct_count']
            
            cumulative_questions += daily_questions
            cumulative_correct += daily_correct
            
            daily_accuracy = (daily_correct / daily_questions * 100) if daily_questions > 0 else 0
            cumulative_accuracy = (cumulative_correct / cumulative_questions * 100) if cumulative_questions > 0 else 0
            
            result.append({
                'date': date_str,
                'questions': daily_questions,
                'correct': daily_correct,
                'daily_accuracy': round(daily_accuracy, 1),
                'cumulative_accuracy': round(cumulative_accuracy, 1)
            })
        
        return result
    finally:
        conn.close()

def get_user_stats_summary(user_id):
    """
    Get summary statistics for the user dashboard
    """
    conn = get_user_db_connection()
    try:
        # Total questions answered
        total_questions = conn.execute(
            'SELECT COUNT(*) as count FROM quiz_answers qa JOIN quiz_history qh ON qa.quiz_history_id = qh.id WHERE qh.user_id = ?',
            (user_id,)
        ).fetchone()['count']
        
        # Total correct answers
        correct_answers = conn.execute(
            'SELECT COUNT(*) as count FROM quiz_answers qa JOIN quiz_history qh ON qa.quiz_history_id = qh.id WHERE qh.user_id = ? AND qa.is_correct = 1',
            (user_id,)
        ).fetchone()['count']
        
        # Overall accuracy
        accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # Number of topics studied (tracked by speciality in topic_performance)
        topics_studied = conn.execute(
            'SELECT COUNT(DISTINCT speciality) as count FROM topic_performance WHERE user_id = ?',
            (user_id,)
        ).fetchone()['count']
        
        # Spaced repetition cards count
        sr_cards = conn.execute(
            'SELECT COUNT(*) as count FROM spaced_repetition WHERE user_id = ?',
            (user_id,)
        ).fetchone()['count']
        
        # Average score from quizzes
        avg_score_query = conn.execute(
            '''SELECT AVG(CASE WHEN total_questions > 0 THEN score * 100.0 / total_questions ELSE 0 END) as avg_score 
               FROM quiz_history WHERE user_id = ?''',
            (user_id,)
        ).fetchone()
        avg_score = avg_score_query['avg_score'] if avg_score_query['avg_score'] is not None else 0
        
        # Get never attempted questions count
        never_attempted = get_never_attempted_count(user_id)
        
        return {
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'accuracy': round(accuracy, 1),
            'topics_studied': topics_studied,
            'sr_cards': sr_cards,
            'avg_score': round(avg_score, 1),
            'never_attempted': never_attempted
        }
    finally:
        conn.close()

def get_never_attempted_count(user_id):
    """
    Get the count of questions the user has never attempted
    """
    conn = get_user_db_connection()
    try:
        # Get total number of questions in the database
        # Note: total questions come from content DB; here we use user DB only for attempted count.
        total_questions_count = 0
        
        # Get number of unique questions the user has attempted
        attempted_questions_count = conn.execute(
            '''SELECT COUNT(DISTINCT qa.question_id) as count 
               FROM quiz_answers qa 
               JOIN quiz_history qh ON qa.quiz_history_id = qh.id 
               WHERE qh.user_id = ?''',
            (user_id,)
        ).fetchone()['count']
        
        # Unknown total in user DB context; return attempted count only
        return max(0, -attempted_questions_count)
    finally:
        conn.close()

def get_day_streak(user_id):
    """
    Calculate the user's current day streak based on consecutive days of activity
    """
    conn = get_user_db_connection()
    try:
        # Get the user's activity dates in descending order
        activity_dates = conn.execute(
            '''SELECT activity_date FROM user_activity 
               WHERE user_id = ? 
               ORDER BY activity_date DESC''',
            (user_id,)
        ).fetchall()
        
        # If no activity, return 0
        if not activity_dates:
            return 0
        
        # Convert to datetime objects
        dates = [datetime.strptime(date['activity_date'], '%Y-%m-%d').date() for date in activity_dates]
        
        today = datetime.now().date()
        
        # Check if today has activity
        streak = 0
        if dates and (dates[0] == today or dates[0] == today - timedelta(days=1)):
            # Start counting streak
            streak = 1
            last_date = dates[0]
            
            # Check each date in sequence for continuity
            for i in range(1, len(dates)):
                # If there's exactly one day difference, continue the streak
                if last_date - dates[i] == timedelta(days=1):
                    streak += 1
                    last_date = dates[i]
                # If same day (duplicate entry), skip
                elif last_date == dates[i]:
                    continue
                # If gap in dates, break the streak
                else:
                    break
        
        return streak
    finally:
        conn.close() 