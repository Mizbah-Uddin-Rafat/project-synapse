"""
MODULE 4 — Batch Prediction Script
====================================
Run predictions for all students and print a risk report.

Usage:
    cd project_synapse
    python ml/predict.py

Requires trained model (run train_model.py first).
"""

import os
import sys
import pickle
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
FEATURE_COLS = [
    'avg_score', 'total_attempts', 'avg_time_taken', 'avg_response_time',
    'total_time_spent', 'completion_rate', 'revisit_count', 'wrong_answer_rate'
]


def load_model():
    model_path = os.path.join(MODEL_DIR, 'student_model.pkl')
    encoder_path = os.path.join(MODEL_DIR, 'label_encoder.pkl')

    if not os.path.exists(model_path):
        print('[ERROR] Model not found. Run ml/train_model.py first.')
        sys.exit(1)

    with open(model_path, 'rb') as f:
        model = pickle.load(f)
    with open(encoder_path, 'rb') as f:
        encoder = pickle.load(f)
    return model, encoder


def predict_all():
    """Predict risk level for every student in the database."""
    from app import create_app
    from app.models import User, QuizAttempt, InteractionLog, StudentProgress

    app = create_app()
    with app.app_context():
        model, encoder = load_model()
        students = User.query.filter_by(role='student').all()

        results = []
        for s in students:
            attempts = QuizAttempt.query.filter_by(user_id=s.id).all()
            if not attempts:
                continue
            logs = InteractionLog.query.filter_by(user_id=s.id).all()
            progress = StudentProgress.query.filter_by(user_id=s.id).all()

            features = {
                'avg_score': np.mean([a.score for a in attempts]),
                'total_attempts': len(attempts),
                'avg_time_taken': np.mean([a.time_taken for a in attempts]),
                'avg_response_time': np.mean([l.response_time for l in logs if l.response_time > 0]) if logs else 0,
                'total_time_spent': sum(l.duration for l in logs),
                'completion_rate': sum(1 for p in progress if p.completed) / max(len(progress), 1) * 100,
                'revisit_count': sum(1 for l in logs if l.action_type == 'revisit'),
                'wrong_answer_rate': np.mean([a.wrong_answers / max(a.total_questions, 1) for a in attempts]),
            }

            X = pd.DataFrame([features])[FEATURE_COLS]
            pred = model.predict(X)[0]
            proba = model.predict_proba(X)[0]
            risk = encoder.inverse_transform([pred])[0]

            results.append({
                'user_id': s.id,
                'name': s.full_name,
                'email': s.email,
                'group': s.group_type,
                'avg_score': round(features['avg_score'], 1),
                'completion_rate': round(features['completion_rate'], 1),
                'risk_level': risk,
                'confidence': round(max(proba) * 100, 1),
            })

        # Print table
        df = pd.DataFrame(results)
        if df.empty:
            print('No students with quiz data found.')
            return

        print('\nPROJECT SYNAPSE — Batch Risk Predictions')
        print('='*70)
        print(df.to_string(index=False))
        print(f'\nRisk Distribution:\n{df["risk_level"].value_counts().to_string()}')

        # Save CSV
        out_path = os.path.join(os.path.dirname(__file__), 'reports', 'predictions.csv')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f'\n[INFO] Predictions saved to {out_path}')


if __name__ == '__main__':
    predict_all()
