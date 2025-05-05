import sqlite3
import os

def add_time_spent_column():
    """
    Migration script to add time_spent column to quiz_history table
    """
    # Get the database path
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'mcq_database.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if the column already exists
    cursor.execute("PRAGMA table_info(quiz_history)")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    
    if 'time_spent' not in column_names:
        print("Adding time_spent column to quiz_history table...")
        cursor.execute("ALTER TABLE quiz_history ADD COLUMN time_spent INTEGER DEFAULT 0")
        conn.commit()
        print("Column added successfully!")
    else:
        print("time_spent column already exists in quiz_history table")
    
    # Close the connection
    conn.close()

if __name__ == "__main__":
    add_time_spent_column() 