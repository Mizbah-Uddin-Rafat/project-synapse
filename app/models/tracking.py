"""
MODULES 3, 5, 6, 8 — Tracking, Recommendation, AI, Experiment Models
======================================================================
InteractionLog   — raw behaviour events (Module 3)
Recommendation   — adaptive content suggestions (Module 5)
AIResponse       — GPT tutor output (Module 6)
ExperimentResult — A/B testing records (Module 8)
"""

from datetime import datetime
from .database import db


# ------------------------------------------------------------------ #
# MODULE 3 — Student Behaviour Tracking
# ------------------------------------------------------------------ #

class InteractionLog(db.Model):
    """
    Granular event log for every learner action.
    This is the primary research data collection table.

    action_type values:
        lesson_open | lesson_close | click | quiz_start |
        quiz_submit | video_play | video_pause | revisit | idle
    """
    __tablename__ = 'interaction_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    duration = db.Column(db.Integer, default=0)         # seconds spent
    clicks = db.Column(db.Integer, default=0)           # click count in session
    response_time = db.Column(db.Float, default=0.0)    # seconds to answer a question
    metadata_json = db.Column(db.Text)                  # arbitrary extra data as JSON

    def __repr__(self):
        return f'<Log user={self.user_id} action={self.action_type} @ {self.timestamp}>'


# ------------------------------------------------------------------ #
# MODULE 5 — Adaptive Recommendation Engine
# ------------------------------------------------------------------ #

class Recommendation(db.Model):
    """
    AI/rule-based content recommendations per student.

    recommendation_type values:
        next_lesson | revision | easier | advanced | practice
    """
    __tablename__ = 'recommendations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recommendation_type = db.Column(db.String(50), nullable=False)
    recommended_content = db.Column(db.Text)   # Lesson title or free-text description
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=True)
    reason = db.Column(db.Text)                # Human-readable explanation
    mastery_at_time = db.Column(db.Float)      # Snapshot for research logs
    acted_on = db.Column(db.Boolean, default=False)  # Did the student follow it?
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Rec user={self.user_id} type={self.recommendation_type}>'


# ------------------------------------------------------------------ #
# MODULE 6 — Generative AI Tutor
# ------------------------------------------------------------------ #

class AIResponse(db.Model):
    """
    Stores every GPT interaction — prompt, response, and context.
    Used for research analysis and audit trail.
    """
    __tablename__ = 'ai_responses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    response_type = db.Column(db.String(50))   # explanation | summary | quiz | revision
    prompt = db.Column(db.Text, nullable=False)
    generated_response = db.Column(db.Text, nullable=False)
    weak_topics = db.Column(db.String(500))    # Topics included in prompt context
    mastery_score = db.Column(db.Float)        # Mastery at prompt generation time
    tokens_used = db.Column(db.Integer, default=0)
    model_used = db.Column(db.String(50), default='gpt-4o-mini')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AIResponse user={self.user_id} type={self.response_type}>'


# ------------------------------------------------------------------ #
# MODULE 8 — A/B Testing
# ------------------------------------------------------------------ #

class ExperimentResult(db.Model):
    """
    Records pre/post scores and engagement for A/B experiment analysis.
    group_type: 'control' (static) | 'experimental' (AI-adaptive)
    """
    __tablename__ = 'experiment_results'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    group_type = db.Column(db.String(20), nullable=False)   # control | experimental
    pre_test_score = db.Column(db.Float, default=0.0)
    post_test_score = db.Column(db.Float, default=0.0)
    engagement_score = db.Column(db.Float, default=0.0)
    completion_rate = db.Column(db.Float, default=0.0)
    total_sessions = db.Column(db.Integer, default=0)
    avg_session_duration = db.Column(db.Float, default=0.0)  # minutes
    ai_interactions = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Experiment user={self.user_id} group={self.group_type}>'
