# Routes package

from app.routes.main import main_bp
from app.routes.profile import profile_bp
from app.routes.quiz import quiz_bp
from app.routes.admin import admin_bp

def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(admin_bp) 