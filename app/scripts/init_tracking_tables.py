import os
import sqlite3
from datetime import datetime, timedelta

def init_tracking_tables():
    """Initialize user tracking tables in the database"""
    # Get the database path
    db_dir = os.path.dirname(os.path.dirname(__file__))
    db_path = os.path.join(db_dir, 'db', 'mcq_database.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create user sessions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT NOT NULL,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')
        
        # Create user activity logs table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL,
            activity_details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')
        
        # Create indices for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON user_activity_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_type ON user_activity_logs(activity_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON user_activity_logs(timestamp)')
        
        # Commit changes
        conn.commit()
        print("User tracking tables initialized successfully!")
        return True
    
    except Exception as e:
        print(f"Error initializing tracking tables: {e}")
        return False
    
    finally:
        conn.close()

def populate_sample_data():
    """Populate sample activity data for testing"""
    db_dir = os.path.dirname(os.path.dirname(__file__))
    db_path = os.path.join(db_dir, 'db', 'mcq_database.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all users
        users = cursor.execute('SELECT id FROM users').fetchall()
        
        # Sample activity types
        activity_types = ['login', 'quiz_start', 'quiz_complete', 'profile_update', 'logout']
        
        # Generate sample activities for the past 30 days
        for user_id in users:
            user_id = user_id[0]
            current_time = datetime.now()
            
            for i in range(30):
                # Random activities for each day
                for _ in range(3):  # 3 activities per day
                    activity_type = activity_types[i % len(activity_types)]
                    timestamp = current_time - timedelta(days=i, hours=i*2)
                    
                    cursor.execute('''
                    INSERT INTO user_activity_logs 
                    (user_id, activity_type, activity_details, timestamp, ip_address)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (
                        user_id,
                        activity_type,
                        f"Sample {activity_type} activity",
                        timestamp,
                        '127.0.0.1'
                    ))
        
        conn.commit()
        print("Sample activity data populated successfully!")
        return True
    
    except Exception as e:
        print(f"Error populating sample data: {e}")
        return False
    
    finally:
        conn.close()

if __name__ == '__main__':
    if init_tracking_tables():
        populate_sample_data() 