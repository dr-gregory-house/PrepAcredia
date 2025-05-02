import os
import sqlite3
import sys

def init_tables():
    """
    Initialize the analytics and spaced repetition tables
    """
    print("Initializing analytics and spaced repetition tables...")
    
    # Get database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(os.path.dirname(script_dir), 'db', 'mcq_database.db')
    sql_file_path = os.path.join(os.path.dirname(script_dir), 'db', 'spaced_repetition.sql')
    
    try:
        with open(sql_file_path, 'r') as f:
            sql_script = f.read()
        
        # Run the SQL script
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(sql_script)
        conn.commit()
        conn.close()
        
        print("Tables created successfully!")
        return True
    except Exception as e:
        print(f"Error initializing tables: {e}")
        return False
    
def populate_existing_data():
    """
    Populate analytics data from existing quiz_history and quiz_answers
    """
    print("Populating topic performance data from existing quiz history...")
    
    # Get database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(os.path.dirname(script_dir), 'db', 'mcq_database.db')
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Get all quiz answers
        answers = conn.execute('''
            SELECT qa.question_id, qa.is_correct, qh.user_id
            FROM quiz_answers qa
            JOIN quiz_history qh ON qa.quiz_history_id = qh.id
        ''').fetchall()
        
        # Process each answer
        for answer in answers:
            user_id = answer['user_id']
            question_id = answer['question_id']
            is_correct = bool(answer['is_correct'])
            
            # Get chapters for this question
            chapters = conn.execute('''
                SELECT chapter_id FROM question_chapters 
                WHERE question_id = ?
            ''', (question_id,)).fetchall()
            
            # Update performance for each chapter
            for chapter in chapters:
                chapter_id = chapter['chapter_id']
                
                # Check if we already have an entry
                existing = conn.execute('''
                    SELECT id, correct_count, incorrect_count 
                    FROM topic_performance 
                    WHERE user_id = ? AND chapter_id = ?
                ''', (user_id, chapter_id)).fetchone()
                
                if existing:
                    # Update existing record
                    correct_count = existing['correct_count'] + (1 if is_correct else 0)
                    incorrect_count = existing['incorrect_count'] + (0 if is_correct else 1)
                    
                    conn.execute('''
                        UPDATE topic_performance 
                        SET correct_count = ?, incorrect_count = ?
                        WHERE id = ?
                    ''', (correct_count, incorrect_count, existing['id']))
                else:
                    # Create new record
                    conn.execute('''
                        INSERT INTO topic_performance 
                        (user_id, chapter_id, correct_count, incorrect_count)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, chapter_id, 1 if is_correct else 0, 0 if is_correct else 1))
        
        # Populate user activity from quiz history
        print("Populating user activity data from quiz history...")
        quizzes = conn.execute('''
            SELECT user_id, quiz_date, score, total_questions
            FROM quiz_history
        ''').fetchall()
        
        for quiz in quizzes:
            user_id = quiz['user_id']
            quiz_date = quiz['quiz_date'].split(' ')[0]  # Get just the date part
            score = quiz['score']
            total = quiz['total_questions']
            
            # Check if we already have an entry for this date
            existing = conn.execute('''
                SELECT id, quiz_count, question_count, correct_count
                FROM user_activity
                WHERE user_id = ? AND activity_date = ?
            ''', (user_id, quiz_date)).fetchone()
            
            if existing:
                # Update existing record
                new_quiz_count = existing['quiz_count'] + 1
                new_question_count = existing['question_count'] + total
                new_correct_count = existing['correct_count'] + score
                
                conn.execute('''
                    UPDATE user_activity
                    SET quiz_count = ?, question_count = ?, correct_count = ?
                    WHERE id = ?
                ''', (new_quiz_count, new_question_count, new_correct_count, existing['id']))
            else:
                # Create new record
                conn.execute('''
                    INSERT INTO user_activity
                    (user_id, activity_date, quiz_count, question_count, correct_count)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, quiz_date, 1, total, score))
        
        conn.commit()
        print("Data population complete!")
        return True
    except Exception as e:
        print(f"Error populating data: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    if init_tables():
        populate_existing_data()
    print("Done!") 