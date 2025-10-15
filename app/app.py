# Version 1.0.2 - Optimized database syncing with Flask g object
from flask import Flask, request, session, g
from flask_wtf.csrf import CSRFProtect
from app.config.config import Config
from app.utils.db import init_db
from app.auth.routes import auth_bp
from app.routes.quiz import quiz_bp
from app.routes.main import main_bp
from app.admin.routes import admin_bp
from app.routes.profile import profile_bp
from app.utils.filters import timeago, format_datetime, init_filters
from app.utils.middleware import track_user_activity
from app.utils.cloud_storage import SyncManager
import os
import logging

# Centralized sync manager
sync_manager = SyncManager()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize CSRF protection
    csrf = CSRFProtect(app)

    # Configure session security settings
    app.config['SESSION_COOKIE_SECURE'] = app.config.get('SESSION_COOKIE_SECURE', False)
    app.config['SESSION_COOKIE_HTTPONLY'] = app.config.get('SESSION_COOKIE_HTTPONLY', True)
    app.config['SESSION_COOKIE_SAMESITE'] = app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['PERMANENT_SESSION_LIFETIME'] = app.config.get('PERMANENT_SESSION_LIFETIME', 3600)

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
        # Centralized startup sync
        sync_manager.on_startup(app)
        init_db()

    # Initialize db_changed flag for each request
    @app.before_request
    def init_request_context():
        """Initialize request-specific context variables"""
        g.db_changed = False
        g.significant_db_change = False  # For major changes like quiz completion
    
    # Register activity tracking middleware
    @app.before_request
    @track_user_activity()
    def track_activity():
        pass

    # Centralized sync after each request
    @app.after_request
    def maybe_sync(response):
        try:
            user_active = ('user_id' in session)
            # Use significant_db_change flag for optimized syncing
            db_changed = getattr(g, 'significant_db_change', False)
            sync_manager.on_request_end(app, db_changed, user_active)
        except Exception:
            # Best-effort; never break response
            pass
        return response

    # Best-effort sync on shutdown/teardown
    @app.teardown_appcontext
    def on_shutdown(exc):
        try:
            sync_manager.on_shutdown(app)
        except Exception:
            pass

    return app
