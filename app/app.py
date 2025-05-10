# Version 1.0.1 - Removed before_first_request for Flask 2.0+ compatibility
from flask import Flask, request
from app.config.config import Config
from app.utils.db import init_db, sync_db_to_cloud
from app.auth.routes import auth_bp
from app.routes.quiz import quiz_bp
from app.routes.main import main_bp
from app.admin.routes import admin_bp
from app.routes.profile import profile_bp
from app.utils.filters import timeago, format_datetime, init_filters
from app.utils.middleware import track_user_activity
import os
import logging
import time
import atexit
import threading

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for sync tracking
last_sync_time = 0
db_changed = False
SYNC_INTERVAL = 900  # 15 minutes in seconds

# Function for background thread
def scheduled_sync():
    global db_changed, last_sync_time
    while True:
        time.sleep(SYNC_INTERVAL * 15)  # 15 times the normal interval as a backup
        from flask import current_app
        if os.environ.get('K_SERVICE') and db_changed:
            try:
                with current_app.app_context():
                    sync_db_to_cloud()
                    last_sync_time = time.time()
                    db_changed = False
                    logger.info("Scheduled database sync completed")
            except Exception as e:
                logger.error(f"Error in scheduled sync: {str(e)}")

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(profile_bp)
    
    # Register filters
    init_filters(app)
    app.jinja_env.filters['timeago'] = timeago
    app.jinja_env.filters['format_datetime'] = format_datetime
    
    # Initialize the database within app context
    with app.app_context():
        init_db()
    
    # Register activity tracking middleware
    @app.before_request
    @track_user_activity()
    def track_activity():
        pass
    
    # Add after_request handler with optimized syncing
    @app.after_request
    def sync_db_after_request(response):
        global last_sync_time, db_changed
        current_time = time.time()
        
        # Track if this request likely modified the database
        if request.method in ['POST', 'PUT', 'DELETE']:
            db_changed = True
        
        # Only sync if in Cloud Run, database changed, and enough time has passed since last sync
        if (os.environ.get('K_SERVICE') and 
            db_changed and 
            current_time - last_sync_time > SYNC_INTERVAL):
            try:
                with app.app_context():
                    sync_db_to_cloud()
                    last_sync_time = current_time
                    db_changed = False
                    logger.info("Database synced to cloud storage (interval-based)")
            except Exception as e:
                logger.error(f"Error syncing database: {str(e)}")
        
        return response
    
    # Register shutdown hook for final sync
    def sync_on_shutdown():
        if os.environ.get('K_SERVICE') and db_changed:
            try:
                with app.app_context():
                    sync_db_to_cloud()
                    logger.info("Final database sync completed on shutdown")
            except Exception as e:
                logger.error(f"Error in shutdown sync: {str(e)}")
    
    if os.environ.get('K_SERVICE'):
        atexit.register(sync_on_shutdown)
    
    # Start background thread for scheduled syncing directly (Flask 2.0+ compatible)
    # NO before_first_request here - it's not supported in Flask 2.0+
    if os.environ.get('K_SERVICE'):
        sync_thread = threading.Thread(target=scheduled_sync)
        sync_thread.daemon = True
        sync_thread.start()
        logger.info("Background database sync thread started")
    
    return app 