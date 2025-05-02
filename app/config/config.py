import os

class Config:
    SECRET_KEY = 'your_secret_key_here'  # Replace with a secure key in production
    
    # Database
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'mcq_database.db')
    
    # Temp directory for quiz data
    TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
    
    # Debug flag
    DEBUG = True 