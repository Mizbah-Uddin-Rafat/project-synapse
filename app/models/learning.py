"""
MODULE 2 — Learning Management Models
======================================
Courses, Lessons, Quizzes, Questions, StudentProgress
"""

from datetime import datetime
from .database import db


class Course(db.Model):
    """Top-level learning container."""
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))          # e.g. 'Mathematics', 'Physics'
    difficulty = db.Column(db.String(20), default='beginner')  # beginner|intermediate|advanced
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    lessons = db.relationship('Lesson', backref='course', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Course {self.title}>'


class Lesson(db.Model):
    """Individual lesson within a course."""
    __tablename__ = 'lessons'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)                   # Rich text / markdown content
    video_url = db.Column(db.String(500))           # Optional embedded video
    topic_category = db.Column(db.String(100))      # Sub-topic tag for ML features
    difficulty = db.Column(db.String(20), default='beginner')
    order_index = db.Column(db.Integer, default=0)  # Lesson ordering within course
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    quizzes = db.relationship('Quiz', backref='lesson', lazy='dynamic')
    interaction_logs = db.relationship('InteractionLog', backref='lesson', lazy='dynamic')
    progress_records = db.relationship('StudentProgress', backref='lesson', lazy='dynamic')

    def __repr__(self):
        return f'<Lesson {self.title}>'


class Quiz(db.Model):
    """Quiz attached to a lesson."""
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    time_limit = db.Column(db.Integer, default=0)   # seconds; 0 = unlimited
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    questions = db.relationship('Question', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy='dynamic')

    def __repr__(self):
        return f'<Quiz {self.title}>'


class Question(db.Model):
    """Multiple-choice question within a quiz."""
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # 'A' | 'B' | 'C' | 'D'
    topic_tag = db.Column(db.String(100))                      # For weak-topic identification
    difficulty = db.Column(db.String(20), default='medium')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Question {self.id}: {self.question_text[:40]}>'


class QuizAttempt(db.Model):
    """
    Records every quiz attempt by a student.
    Key ML feature source.
    """
    __tablename__ = 'quiz_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    score = db.Column(db.Float, default=0.0)          # Percentage 0–100
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    wrong_answers = db.Column(db.Integer, default=0)
    time_taken = db.Column(db.Integer, default=0)     # Seconds
    attempt_number = db.Column(db.Integer, default=1) # Retry count
    answers_json = db.Column(db.Text)                 # JSON dump of answers given
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Attempt user={self.user_id} quiz={self.quiz_id} score={self.score}>'


class StudentProgress(db.Model):
    """
    Tracks per-lesson progress for each student.
    Used in dashboards and ML features.
    """
    __tablename__ = 'student_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completion_percentage = db.Column(db.Float, default=0.0)
    mastery_score = db.Column(db.Float, default=0.0)    # ML-predicted mastery 0–100
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'lesson_id', name='uq_user_lesson'),
    )

    def __repr__(self):
        return f'<Progress user={self.user_id} lesson={self.lesson_id} {self.completion_percentage}%>'