"""
MODULE 4 — Student Modelling Engine: Training Script
======================================================
Trains a Random Forest (or XGBoost) classifier to predict student risk level.

Usage:
    cd project_synapse
    python ml/train_model.py

Output:
    ml/models/student_model.pkl
    ml/models/label_encoder.pkl
    ml/models/feature_names.pkl
    ml/reports/training_report.txt

The model predicts risk_level: low | medium | high
based on quiz scores, time, engagement and completion features.
"""

import os
import sys
import pickle
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server environments
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, classification_report, confusion_matrix
)
from sklearn.pipeline import Pipeline

warnings.filterwarnings('ignore')

# ------------------------------------------------------------------ #
# Paths
# ------------------------------------------------------------------ #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, 'models')
REPORT_DIR = os.path.join(BASE_DIR, 'reports')
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ------------------------------------------------------------------ #
# Step 1 — Load data from MySQL via SQLAlchemy
# ------------------------------------------------------------------ #

def load_data_from_db():
    """
    Pull feature data from the live database.
    Falls back to synthetic data if DB is empty (useful for first-run testing).
    """
    # Add project root to path for app import
    sys.path.insert(0, os.path.join(BASE_DIR, '..'))
    from dotenv import load_dotenv
    load_dotenv()

    try:
        from app import create_app
        from app.models import User, QuizAttempt, InteractionLog, StudentProgress

        app = create_app()
        with app.app_context():
            students = User.query.filter_by(role='student').all()
            rows = []
            for s in students:
                attempts = QuizAttempt.query.filter_by(user_id=s.id).all()
                if not attempts:
                    continue
                logs = InteractionLog.query.filter_by(user_id=s.id).all()
                progress = StudentProgress.query.filter_by(user_id=s.id).all()

                avg_score = np.mean([a.score for a in attempts])
                total_attempts = len(attempts)
                avg_time = np.mean([a.time_taken for a in attempts])
                avg_response_time = np.mean(
                    [l.response_time for l in logs if l.response_time > 0]
                ) if logs else 0.0
                total_time = sum(l.duration for l in logs)
                completion = (
                    sum(1 for p in progress if p.completed) / len(progress) * 100
                ) if progress else 0.0
                revisits = sum(1 for l in logs if l.action_type == 'revisit')
                wrong_rate = np.mean(
                    [a.wrong_answers / max(a.total_questions, 1) for a in attempts]
                )

                # Derive risk label from mastery heuristic
                if avg_score < 40 or completion < 25:
                    risk = 'high'
                elif avg_score < 65 or completion < 60:
                    risk = 'medium'
                else:
                    risk = 'low'

                rows.append({
                    'avg_score': avg_score,
                    'total_attempts': total_attempts,
                    'avg_time_taken': avg_time,
                    'avg_response_time': avg_response_time,
                    'total_time_spent': total_time,
                    'completion_rate': completion,
                    'revisit_count': revisits,
                    'wrong_answer_rate': wrong_rate,
                    'risk_level': risk,
                })

            if len(rows) >= 10:
                return pd.DataFrame(rows)

    except Exception as e:
        print(f'[INFO] Could not load from DB ({e}). Using synthetic data.')

    return _generate_synthetic_data()


def _generate_synthetic_data(n_samples: int = 500) -> pd.DataFrame:
    """
    Generate realistic synthetic student data for model bootstrapping.
    Ensures balanced classes for meaningful evaluation.
    """
    np.random.seed(42)
    n = n_samples

    # High-risk students (n/3)
    high = pd.DataFrame({
        'avg_score':        np.random.normal(35, 10, n // 3).clip(0, 60),
        'total_attempts':   np.random.randint(1, 5, n // 3).astype(float),
        'avg_time_taken':   np.random.normal(120, 30, n // 3).clip(10, 600),
        'avg_response_time': np.random.normal(40, 10, n // 3).clip(1, 120),
        'total_time_spent': np.random.normal(600, 200, n // 3).clip(0, 3000),
        'completion_rate':  np.random.normal(20, 10, n // 3).clip(0, 40),
        'revisit_count':    np.random.randint(0, 3, n // 3).astype(float),
        'wrong_answer_rate': np.random.normal(0.7, 0.1, n // 3).clip(0.4, 1.0),
        'risk_level':       'high',
    })

    # Medium-risk students (n/3)
    medium = pd.DataFrame({
        'avg_score':        np.random.normal(60, 10, n // 3).clip(40, 79),
        'total_attempts':   np.random.randint(3, 8, n // 3).astype(float),
        'avg_time_taken':   np.random.normal(90, 20, n // 3).clip(10, 300),
        'avg_response_time': np.random.normal(25, 8, n // 3).clip(1, 60),
        'total_time_spent': np.random.normal(2000, 500, n // 3).clip(500, 6000),
        'completion_rate':  np.random.normal(55, 15, n // 3).clip(30, 80),
        'revisit_count':    np.random.randint(2, 6, n // 3).astype(float),
        'wrong_answer_rate': np.random.normal(0.4, 0.1, n // 3).clip(0.2, 0.6),
        'risk_level':       'medium',
    })

    # Low-risk students (n - 2*(n/3))
    remaining = n - 2 * (n // 3)
    low = pd.DataFrame({
        'avg_score':        np.random.normal(82, 8, remaining).clip(70, 100),
        'total_attempts':   np.random.randint(5, 15, remaining).astype(float),
        'avg_time_taken':   np.random.normal(70, 15, remaining).clip(10, 200),
        'avg_response_time': np.random.normal(15, 5, remaining).clip(1, 40),
        'total_time_spent': np.random.normal(4000, 800, remaining).clip(2000, 10000),
        'completion_rate':  np.random.normal(85, 10, remaining).clip(70, 100),
        'revisit_count':    np.random.randint(3, 10, remaining).astype(float),
        'wrong_answer_rate': np.random.normal(0.15, 0.07, remaining).clip(0.0, 0.3),
        'risk_level':       'low',
    })

    df = pd.concat([high, medium, low], ignore_index=True).sample(frac=1, random_state=42)
    print(f'[INFO] Generated {len(df)} synthetic student records.')
    return df


# ------------------------------------------------------------------ #
# Step 2 — Train
# ------------------------------------------------------------------ #

FEATURE_COLS = [
    'avg_score', 'total_attempts', 'avg_time_taken', 'avg_response_time',
    'total_time_spent', 'completion_rate', 'revisit_count', 'wrong_answer_rate'
]


def train(df: pd.DataFrame):
    """Full training pipeline."""
    print(f'\n{"="*60}')
    print('PROJECT SYNAPSE — Student Modelling Engine')
    print('Training Random Forest Risk Classifier')
    print(f'{"="*60}\n')

    X = df[FEATURE_COLS]
    y_raw = df['risk_level']

    # Encode labels
    encoder = LabelEncoder()
    y = encoder.fit_transform(y_raw)
    print(f'Classes: {encoder.classes_}')
    print(f'Class distribution:\n{pd.Series(y_raw).value_counts()}\n')

    # Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f'Train: {len(X_train)} | Test: {len(X_test)}')

    # Model
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='f1_weighted')
    print(f'5-Fold CV F1-weighted: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}')

    # Final fit
    model.fit(X_train, y_train)

    # Evaluation
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average='weighted', zero_division=0)
    rec = recall_score(y_test, y_pred, average='weighted', zero_division=0)
    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)

    print(f'\n--- Evaluation Metrics ---')
    print(f'Accuracy:  {acc:.4f}')
    print(f'Precision: {prec:.4f}')
    print(f'Recall:    {rec:.4f}')
    print(f'F1-Score:  {f1:.4f}')
    print(f'\n--- Classification Report ---')
    print(classification_report(y_test, y_pred, target_names=encoder.classes_))

    # Feature importance
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print(f'\n--- Feature Importances ---')
    print(importances.to_string())

    # ---- Confusion matrix plot ------------------------------------ #
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=encoder.classes_, yticklabels=encoder.classes_)
    plt.title('Confusion Matrix — Risk Level Prediction')
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'confusion_matrix.png'), dpi=150)
    plt.close()
    print(f'\n[INFO] Confusion matrix saved to ml/reports/confusion_matrix.png')

    # ---- Feature importance plot ---------------------------------- #
    plt.figure(figsize=(10, 6))
    importances.plot(kind='barh', color='steelblue')
    plt.title('Feature Importances — Random Forest')
    plt.xlabel('Importance Score')
    plt.tight_layout()
    plt.savefig(os.path.join(REPORT_DIR, 'feature_importance.png'), dpi=150)
    plt.close()
    print('[INFO] Feature importance chart saved to ml/reports/feature_importance.png')

    # ---- Save artefacts ------------------------------------------- #
    with open(os.path.join(MODEL_DIR, 'student_model.pkl'), 'wb') as f:
        pickle.dump(model, f)
    with open(os.path.join(MODEL_DIR, 'label_encoder.pkl'), 'wb') as f:
        pickle.dump(encoder, f)
    with open(os.path.join(MODEL_DIR, 'feature_names.pkl'), 'wb') as f:
        pickle.dump(FEATURE_COLS, f)

    print(f'\n[SUCCESS] Model saved to ml/models/student_model.pkl')

    # ---- Write text report ---------------------------------------- #
    report_text = f"""PROJECT SYNAPSE — Training Report
{'='*50}
Samples: {len(df)}
Features: {FEATURE_COLS}
Classes: {list(encoder.classes_)}

Evaluation Metrics
------------------
Accuracy:  {acc:.4f}
Precision: {prec:.4f}
Recall:    {rec:.4f}
F1-Score:  {f1:.4f}
CV F1:     {cv_scores.mean():.3f} ± {cv_scores.std():.3f}

{classification_report(y_test, y_pred, target_names=encoder.classes_)}
"""
    with open(os.path.join(REPORT_DIR, 'training_report.txt'), 'w') as f:
        f.write(report_text)

    print('[INFO] Training report saved to ml/reports/training_report.txt')
    return model, encoder


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == '__main__':
    df = load_data_from_db()
    train(df)
