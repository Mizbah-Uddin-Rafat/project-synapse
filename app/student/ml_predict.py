"""
MODULE 4 — Real-time ML Prediction Service
==========================================
Loads the trained model and produces predictions for a single student.
Called after every quiz submission.
"""

import os
import pickle
import numpy as np
import pandas as pd
from ..models import (db, User, QuizAttempt, InteractionLog,
                      StudentProgress, Recommendation)
from ..analytics.analytics_service import get_student_summary

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'ml', 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'student_model.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')


def predict_student(user_id: int) -> dict | None:
    """
    Load the trained model and predict mastery / risk for a student.
    Returns prediction dict or None if model not trained yet.
    """
    if not os.path.exists(MODEL_PATH):
        return None  # Model not trained yet — train_model.py hasn't been run

    try:
        with open(MODEL_PATH, 'rb') as f:
            model = pickle.load(f)
        with open(ENCODER_PATH, 'rb') as f:
            encoder = pickle.load(f)
    except Exception:
        return None

    # Build feature vector
    features = _build_features(user_id)
    if features is None:
        return None

    X = pd.DataFrame([features])
    pred_encoded = model.predict(X)[0]
    pred_proba = model.predict_proba(X)[0]

    risk_label = encoder.inverse_transform([pred_encoded])[0]
    risk_prob = max(pred_proba)

    # Persist prediction to progress records
    summary = get_student_summary(user_id)
    progress_records = StudentProgress.query.filter_by(user_id=user_id).all()
    for p in progress_records:
        p.mastery_score = summary['mastery_score']
    db.session.commit()

    return {
        'risk_level': risk_label,
        'risk_probability': round(float(risk_prob), 3),
        'mastery_score': summary['mastery_score'],
        'weak_topics': summary['weak_topics'],
    }


def _build_features(user_id: int) -> dict | None:
    """
    Extract ML feature vector for one student.
    Must match the feature set used during training.
    """
    attempts = QuizAttempt.query.filter_by(user_id=user_id).all()
    if not attempts:
        return None

    logs = InteractionLog.query.filter_by(user_id=user_id).all()
    progress = StudentProgress.query.filter_by(user_id=user_id).all()

    avg_score = np.mean([a.score for a in attempts]) if attempts else 0.0
    total_attempts = len(attempts)
    avg_time = np.mean([a.time_taken for a in attempts]) if attempts else 0.0
    avg_response_time = np.mean([l.response_time for l in logs if l.response_time > 0]) if logs else 0.0
    total_time_spent = sum(l.duration for l in logs)
    completion_rate = (
        sum(1 for p in progress if p.completed) / len(progress) * 100
    ) if progress else 0.0
    revisit_count = sum(1 for l in logs if l.action_type == 'revisit')
    wrong_answer_rate = np.mean([a.wrong_answers / max(a.total_questions, 1) for a in attempts]) if attempts else 0.0

    return {
        'avg_score': avg_score,
        'total_attempts': total_attempts,
        'avg_time_taken': avg_time,
        'avg_response_time': avg_response_time,
        'total_time_spent': total_time_spent,
        'completion_rate': completion_rate,
        'revisit_count': revisit_count,
        'wrong_answer_rate': wrong_answer_rate,
    }
