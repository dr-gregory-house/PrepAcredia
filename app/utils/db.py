import sqlite3
import os
import logging
from flask import current_app, g

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(current_app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with user tables if they don't exist"""
    # This will be called with app context from create_app
    
    # First check if we're running in Cloud Run
    if os.environ.get('K_SERVICE'):
        # Download DB from Cloud Storage if in Cloud Run
        try:
            from app.utils.cloud_storage import download_db_from_bucket
            download_db_from_bucket()
            logger.info("Database downloaded from Cloud Storage")
        except ImportError:
            logger.error("Could not import cloud_storage module")
        except Exception as e:
            logger.error(f"Error downloading database: {str(e)}")
    
    # Ensure db directory exists
    db_dir = os.path.dirname(current_app.config['DB_PATH'])
    os.makedirs(db_dir, exist_ok=True)
    
    # Ensure temp directory exists
    os.makedirs(current_app.config['TEMP_DIR'], exist_ok=True)
    
    conn = get_db_connection()
    
    # Check if chapters table exists
    chapters_exists = False
    try:
        # This will raise an OperationalError if the table doesn't exist
        conn.execute('SELECT 1 FROM chapters LIMIT 1')
        chapters_exists = True
    except sqlite3.OperationalError:
        # Table doesn't exist, we'll create it later
        pass
    
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
    
    # Only create chapters and related tables if they don't exist
    if not chapters_exists:
        logger.info("Creating chapters and related tables...")
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            FOREIGN KEY (parent_id) REFERENCES chapters (id)
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,
            explanation TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS question_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions (id),
            FOREIGN KEY (chapter_id) REFERENCES chapters (id)
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
        ''')
        
        conn.execute('''
        CREATE TABLE IF NOT EXISTS question_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions (id),
            FOREIGN KEY (tag_id) REFERENCES tags (id)
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
        INSERT INTO users (username, email, name, role, is_active)
        VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@example.com', 'Admin User', 'admin', 1))
    
    conn.commit()
    conn.close()
    
    # Upload the initialized database back to Cloud Storage if in Cloud Run
    if os.environ.get('K_SERVICE'):
        try:
            from app.utils.cloud_storage import upload_db_to_bucket
            upload_db_to_bucket()
            logger.info("Database uploaded to Cloud Storage after initialization")
        except ImportError:
            logger.error("Could not import cloud_storage module")
        except Exception as e:
            logger.error(f"Error uploading database: {str(e)}")

def sync_db_to_cloud():
    """Sync the current database state to cloud storage"""
    if os.environ.get('K_SERVICE'):
        try:
            from app.utils.cloud_storage import upload_db_to_bucket
            upload_db_to_bucket()
            logger.info("Database synced to Cloud Storage")
            return True
        except Exception as e:
            logger.error(f"Error syncing database to cloud: {str(e)}")
            return False
    return False 