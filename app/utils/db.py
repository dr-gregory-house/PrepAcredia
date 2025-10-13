import sqlite3
import os
import logging
from flask import current_app
from app.scripts.init_tracking_tables import init_tracking_tables

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_content_db_connection():
    """Get a read-only connection to the content SQLite database (master.db)."""
    db_path = current_app.config['CONTENT_DB_PATH']
    # Content DB is read-only; however sqlite3 in Python doesn't enforce read-only easily without URI.
    # Use URI mode to open in read-only. Fallback to normal open if URI fails (e.g., Windows paths).
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_db_connection():
    """Get a connection to the user/admin SQLite database (user.db)."""
    db_path = current_app.config['USER_DB_PATH']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize user database (user.db) and ensure temp directories exist."""
    # This will be called with app context from create_app
    
    # Ensure user db directory exists
    user_db_dir = os.path.dirname(current_app.config['USER_DB_PATH'])
    os.makedirs(user_db_dir, exist_ok=True)
    
    # Ensure temp directory exists
    os.makedirs(current_app.config['TEMP_DIR'], exist_ok=True)
    
    conn = get_user_db_connection()
    
    # Create user/admin and analytics schemas in user.db
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT,
        profile_picture TEXT,
        role TEXT DEFAULT 'user',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS quiz_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quiz_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        score INTEGER NOT NULL,
        total_questions INTEGER NOT NULL,
        selected_specialities TEXT,
        time_spent INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS quiz_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_history_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        selected_letter TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        FOREIGN KEY (quiz_history_id) REFERENCES quiz_history (id)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS spaced_repetition (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        next_review TIMESTAMP NOT NULL,
        repetition_count INTEGER DEFAULT 1,
        difficulty_level INTEGER DEFAULT 3,
        UNIQUE(user_id, question_id)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS topic_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        speciality TEXT NOT NULL,
        correct_count INTEGER DEFAULT 0,
        incorrect_count INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, speciality)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS user_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        activity_date DATE NOT NULL,
        quiz_count INTEGER DEFAULT 0,
        question_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        UNIQUE(user_id, activity_date)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS user_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_token TEXT NOT NULL,
        login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        ip_address TEXT,
        user_agent TEXT
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS user_activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        activity_details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ip_address TEXT
    )
    ''')

    # Indices for performance
    conn.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON user_activity_logs(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_type ON user_activity_logs(activity_type)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON user_activity_logs(timestamp)')

    # Initialize user tracking tables (no-op if already created)
    init_tracking_tables()
    
    # Create default admin user if not exists
    admin_exists = conn.execute('SELECT 1 FROM users WHERE role = "admin" LIMIT 1').fetchone()
    if not admin_exists:
        conn.execute('''
        INSERT INTO users (username, email, name, role, is_active)
        VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@example.com', 'Admin User', 'admin', 1))
    
    conn.commit()
    conn.close()
