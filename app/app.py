from flask import Flask
from app.config.config import Config
from app.utils.db import init_db
from app.auth.routes import auth_bp
from app.routes.quiz import quiz_bp
from app.routes.main import main_bp
from app.admin.routes import admin_bp
from app.routes.profile import profile_bp

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
    
    from app.utils.filters import init_filters
    init_filters(app)
    
    return app 