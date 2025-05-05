import os

class Config:
    SECRET_KEY = 'your_secret_key_here'  # Replace with a secure key in production
    
    # Database
    # In Cloud Run, use /tmp directory which is writable
    if os.environ.get('K_SERVICE'):  # This environment variable is set in Cloud Run
        DB_PATH = '/tmp/mcq_database.db'
        TEMP_DIR = '/tmp/pedia_temp'
    else:
        # Local development
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'mcq_database.db')
        TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
    
    # Debug flag
    DEBUG = True 