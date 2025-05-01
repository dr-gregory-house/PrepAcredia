import sqlite3
import os
from flask import current_app, g

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(current_app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with user tables if they don't exist"""
    # This will be called with app context from create_app
    
    # Ensure db directory exists
    db_dir = os.path.dirname(current_app.config['DB_PATH'])
    os.makedirs(db_dir, exist_ok=True)
    
    # Ensure temp directory exists
    os.makedirs(current_app.config['TEMP_DIR'], exist_ok=True)
    
    conn = get_db_connection()
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT,
        google_id TEXT UNIQUE,
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
        selected_chapters TEXT NOT NULL,
        selected_tags TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.execute('''
    CREATE TABLE IF NOT EXISTS quiz_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_history_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        selected_answer TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        FOREIGN KEY (quiz_history_id) REFERENCES quiz_history (id),
        FOREIGN KEY (question_id) REFERENCES questions (id)
    )
    ''')
    
    # Create default admin user if not exists
    admin_exists = conn.execute('SELECT 1 FROM users WHERE role = "admin" LIMIT 1').fetchone()
    if not admin_exists:
        conn.execute('''
        INSERT INTO users (email, name, role, is_active)
        VALUES (?, ?, ?, ?)
        ''', ('admin@example.com', 'Admin User', 'admin', 1))
    
    conn.commit()
    conn.close() 