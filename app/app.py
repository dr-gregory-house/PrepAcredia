from flask import Flask, request
from app.config.config import Config
from app.utils.db import init_db, sync_db_to_cloud
from app.auth.routes import auth_bp
from app.routes.quiz import quiz_bp
from app.routes.main import main_bp
from app.admin.routes import admin_bp
from app.routes.profile import profile_bp
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(profile_bp)
    
    # Initialize the database within app context
    with app.app_context():
        init_db()
    
    # Add after_request handler to sync database to cloud storage
    # Only sync after POST, PUT, DELETE requests that likely modified the database
    @app.after_request
    def sync_db_after_request(response):
        if os.environ.get('K_SERVICE') and request.method in ['POST', 'PUT', 'DELETE']:
            try:
                with app.app_context():
                    sync_db_to_cloud()
            except Exception as e:
                logger.error(f"Error syncing database: {str(e)}")
        return response
    
    from app.utils.filters import init_filters
    init_filters(app)
    
    return app 