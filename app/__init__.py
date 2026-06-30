"""
PROJECT SYNAPSE — Main Application Factory
==========================================
An AI-Powered Personalised Learning Ecosystem
"""

import os
from flask import Flask, app
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from .models.database import db
from .models.user import User

# Load environment variables
load_dotenv()

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config=None):
    """Application factory — creates and configures the Flask app."""
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
    database_url = os.getenv('DATABASE_URL', 'mysql+pymysql://root:password@localhost/synapse_db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False  # Set True to debug SQL queries
    app.config['WTF_CSRF_ENABLED'] = True

    if config:
        app.config.update(config)

    # ------------------------------------------------------------------ #
    # Extensions
    # ------------------------------------------------------------------ #
    db.init_app(app)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # ------------------------------------------------------------------ #
    # User loader
    # ------------------------------------------------------------------ #
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ------------------------------------------------------------------ #
    # Register Blueprints
    # ------------------------------------------------------------------ #
    from .auth.routes import auth_bp
    from .student.routes import student_bp
    from .admin.routes import admin_bp
    from .ai.routes import ai_bp
    from .analytics.routes import analytics_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(ai_bp, url_prefix='/ai')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')

    # ------------------------------------------------------------------ #
    # Main index redirect
    # ------------------------------------------------------------------ #
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.dashboard'))
        return redirect(url_for('auth.login'))

    # ------------------------------------------------------------------ #
    # Create tables (dev only — use migrations in production)
    # ------------------------------------------------------------------ #
    

    return app
