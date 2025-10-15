import os
import secrets

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or secrets.token_urlsafe(32)

    # Session configuration
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

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

    # Debug flag - should be False in production
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    # Sync controls - Optimized for reduced frequency
    # Download DB on startup to get latest data
    SYNC_ON_STARTUP = os.environ.get('SYNC_ON_STARTUP', 'True').lower() == 'true'
    
    # Upload DB on shutdown (best-effort)
    SYNC_ON_SHUTDOWN = os.environ.get('SYNC_ON_SHUTDOWN', 'True').lower() == 'true'
    
    # Debounce time between uploads (prevents rapid successive syncs)
    # Increased from 10s to 30s to reduce unnecessary uploads
    SYNC_DEBOUNCE_SECONDS = int(os.environ.get('SYNC_DEBOUNCE_SECONDS', '30'))
    
    # Periodic backup when there are changes
    # This is a safety net - only triggers if DB has changed AND interval has passed
    SYNC_HOURLY_ON_ACTIVITY = os.environ.get('SYNC_HOURLY_ON_ACTIVITY', 'True').lower() == 'true'
    
    # Hourly interval for periodic backups (only if DB has changes)
    # Increased from 1 hour to 2 hours to reduce frequency
    SYNC_HOURLY_INTERVAL = int(os.environ.get('SYNC_HOURLY_INTERVAL', '7200'))
