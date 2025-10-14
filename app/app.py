# Version 1.0.1 - Removed before_first_request for Flask 2.0+ compatibility
from flask import Flask, request
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
import os
import logging

# Global variable to track database changes - needed for auth routes
db_changed = False

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
        init_db()

    # Register activity tracking middleware
    @app.before_request
    @track_user_activity()
    def track_activity():
        pass

    return app
