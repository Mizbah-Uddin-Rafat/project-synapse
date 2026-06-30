"""
MODULE 1 — User Model
=====================
Handles authentication, roles, and session management.
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .database import db


class User(UserMixin, db.Model):
    """
    Core user model supporting Student and Admin/Researcher roles.
    Roles: 'student' | 'admin'
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # 'student' | 'admin'

    # A/B Testing group assignment — set on registration
    group_type = db.Column(db.String(20), default='control')  # 'control' | 'experimental'

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    progress = db.relationship('StudentProgress', backref='user', lazy='dynamic')
    interaction_logs = db.relationship('InteractionLog', backref='user', lazy='dynamic')
    quiz_attempts = db.relationship('QuizAttempt', backref='user', lazy='dynamic')
    recommendations = db.relationship('Recommendation', backref='user', lazy='dynamic')
    ai_responses = db.relationship('AIResponse', backref='user', lazy='dynamic')
    experiment_results = db.relationship('ExperimentResult', backref='user', lazy='dynamic')

    # ------------------------------------------------------------------ #
    # Password helpers
    # ------------------------------------------------------------------ #
    def set_password(self, password):
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a plaintext password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #
    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'