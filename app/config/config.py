import os

class Config:
    SECRET_KEY = 'your_secret_key_here'  # Replace with a secure key in production
    
    # Database
    # In Cloud Run, use /tmp directory which is writable
    if os.environ.get('K_SERVICE'):  # This environment variable is set in Cloud Run
        # Content DB is read-only and bundled/deployed separately; keep under /workspace if needed
        CONTENT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'master.db')
        # User DB is writable and will be synced; use /tmp in Cloud Run
        USER_DB_PATH = '/tmp/user.db'
        TEMP_DIR = '/tmp/pedia_temp'
    else:
        # Local development
        CONTENT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'master.db')
        USER_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'user.db')
        TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
    
    # Debug flag
    DEBUG = True 