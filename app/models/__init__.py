"""
Models package — centralised imports.
Usage:  from app.models import User, Course, Lesson, ...
"""

from .database import db
from .user import User
from .learning import Course, Lesson, Quiz, Question, QuizAttempt, StudentProgress
from .tracking import InteractionLog, Recommendation, AIResponse, ExperimentResult

__all__ = [
    'db',
    'User',
    'Course', 'Lesson', 'Quiz', 'Question', 'QuizAttempt', 'StudentProgress',
    'InteractionLog', 'Recommendation', 'AIResponse', 'ExperimentResult',
]
