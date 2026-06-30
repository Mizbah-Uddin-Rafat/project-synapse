"""
MODULE 7 — Learning Analytics Service
=======================================
Computes per-student and platform-wide metrics.
Used by both student and admin dashboards.
"""

import json
from datetime import datetime, timedelta
from sqlalchemy import func
from ..models import (db, User, Lesson, Course, Quiz, QuizAttempt,
                      StudentProgress, InteractionLog, Recommendation,
                      AIResponse, ExperimentResult)


# ================================================================== #
# STUDENT-LEVEL ANALYTICS
# ================================================================== #

def get_student_summary(user_id: int) -> dict:
    """
    Return a full analytics summary for one student.
    This is the primary data structure powering the student dashboard
    and ML model inputs.
    """
    # ---- Quiz performance ----------------------------------------- #
    attempts = QuizAttempt.query.filter_by(user_id=user_id).all()
    avg_score = (sum(a.score for a in attempts) / len(attempts)) if attempts else 0.0
    total_attempts = len(attempts)
    recent_scores = [a.score for a in sorted(attempts, key=lambda x: x.created_at)[-10:]]

    # ---- Weak topics ---------------------------------------------- #
    weak_topics = _compute_weak_topics(user_id, attempts)

    # ---- Mastery score -------------------------------------------- #
    mastery_score = _compute_mastery(user_id, attempts)

    # ---- Engagement score ----------------------------------------- #
    engagement_score = _compute_engagement(user_id)

    # ---- Lesson completion ---------------------------------------- #
    total_lessons = Lesson.query.count()
    completed = StudentProgress.query.filter_by(user_id=user_id, completed=True).count()
    completion_rate = (completed / total_lessons * 100) if total_lessons > 0 else 0.0

    # ---- Time spent ----------------------------------------------- #
    time_logs = InteractionLog.query.filter_by(user_id=user_id).all()
    total_time_minutes = sum(log.duration for log in time_logs) / 60

    # ---- Recent activity ------------------------------------------ #
    recent_logs = (
        InteractionLog.query
        .filter_by(user_id=user_id)
        .filter(InteractionLog.timestamp >= datetime.utcnow() - timedelta(days=7))
        .count()
    )

    return {
        'mastery_score': round(mastery_score, 2),
        'avg_quiz_score': round(avg_score, 2),
        'total_attempts': total_attempts,
        'recent_scores': recent_scores,
        'weak_topics': weak_topics,
        'engagement_score': round(engagement_score, 2),
        'completion_rate': round(completion_rate, 2),
        'completed_lessons': completed,
        'total_lessons': total_lessons,
        'total_time_minutes': round(total_time_minutes, 1),
        'recent_activity_7d': recent_logs,
    }


def get_progress_over_time(user_id: int) -> list:
    """Return list of {date, score} dicts for Chart.js mastery progression."""
    attempts = (
        QuizAttempt.query
        .filter_by(user_id=user_id)
        .order_by(QuizAttempt.created_at.asc())
        .all()
    )
    return [
        {
            'date': a.created_at.strftime('%Y-%m-%d'),
            'score': round(a.score, 1),
            'quiz_title': a.quiz.title if a.quiz else 'Quiz',
        }
        for a in attempts
    ]


def get_topic_performance(user_id: int) -> list:
    """Return per-topic average scores for radar chart."""
    attempts = QuizAttempt.query.filter_by(user_id=user_id).all()
    topic_scores: dict[str, list] = {}

    for attempt in attempts:
        if attempt.quiz and attempt.quiz.lesson:
            topic = attempt.quiz.lesson.topic_category or 'General'
            topic_scores.setdefault(topic, []).append(attempt.score)

    return [
        {'topic': t, 'avg_score': round(sum(s) / len(s), 1)}
        for t, s in topic_scores.items()
    ]


# ================================================================== #
# ADMIN / RESEARCH ANALYTICS
# ================================================================== #

def get_platform_overview() -> dict:
    """High-level platform statistics for the admin dashboard."""
    total_students = User.query.filter_by(role='student').count()
    total_courses = Course.query.count()
    total_lessons = Lesson.query.count()
    total_attempts = QuizAttempt.query.count()

    avg_score_row = db.session.query(func.avg(QuizAttempt.score)).scalar()
    avg_score = round(float(avg_score_row or 0), 2)

    # High-risk students (mastery < 40 based on recent attempts)
    high_risk_count = _count_high_risk_students()

    return {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_lessons': total_lessons,
        'total_attempts': total_attempts,
        'avg_platform_score': avg_score,
        'high_risk_count': high_risk_count,
    }


def get_all_students_summary() -> list:
    """Return a summary row per student for admin table."""
    students = User.query.filter_by(role='student').all()
    rows = []
    for s in students:
        summary = get_student_summary(s.id)
        rows.append({
            'id': s.id,
            'name': s.full_name,
            'email': s.email,
            'group': s.group_type,
            'mastery': summary['mastery_score'],
            'avg_score': summary['avg_quiz_score'],
            'engagement': summary['engagement_score'],
            'completion': summary['completion_rate'],
            'risk_level': _risk_label(summary['mastery_score'], summary['engagement_score']),
        })
    return rows


def get_ab_experiment_stats() -> dict:
    """
    Compare control vs experimental group metrics.
    Key data for dissertation analysis.
    """
    groups = ['control', 'experimental']
    stats = {}

    for group in groups:
        user_ids = [
            u.id for u in
            User.query.filter_by(role='student', group_type=group).all()
        ]
        if not user_ids:
            stats[group] = {'count': 0, 'avg_score': 0, 'avg_engagement': 0, 'avg_completion': 0}
            continue

        scores = []
        engagements = []
        completions = []
        for uid in user_ids:
            s = get_student_summary(uid)
            scores.append(s['avg_quiz_score'])
            engagements.append(s['engagement_score'])
            completions.append(s['completion_rate'])

        stats[group] = {
            'count': len(user_ids),
            'avg_score': round(sum(scores) / len(scores), 2) if scores else 0,
            'avg_engagement': round(sum(engagements) / len(engagements), 2) if engagements else 0,
            'avg_completion': round(sum(completions) / len(completions), 2) if completions else 0,
        }

    return stats


def get_engagement_trend(days: int = 30) -> list:
    """Return daily active user count for the last N days."""
    trend = []
    for i in range(days, 0, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        count = (
            db.session.query(func.count(func.distinct(InteractionLog.user_id)))
            .filter(InteractionLog.timestamp.between(day_start, day_end))
            .scalar() or 0
        )
        trend.append({'date': day.strftime('%Y-%m-%d'), 'active_users': count})
    return trend


# ================================================================== #
# STATISTICAL HELPERS (for CSV export / dissertation analysis)
# ================================================================== #

def export_experiment_csv_data() -> list:
    """
    Return raw data rows suitable for CSV export and SPSS/R analysis.
    Includes all metrics needed for T-test / ANOVA.
    """
    students = User.query.filter_by(role='student').all()
    rows = []
    for s in students:
        summary = get_student_summary(s.id)
        exp = ExperimentResult.query.filter_by(user_id=s.id).first()
        rows.append({
            'user_id': s.id,
            'group_type': s.group_type,
            'mastery_score': summary['mastery_score'],
            'avg_quiz_score': summary['avg_quiz_score'],
            'engagement_score': summary['engagement_score'],
            'completion_rate': summary['completion_rate'],
            'total_time_minutes': summary['total_time_minutes'],
            'total_quiz_attempts': summary['total_attempts'],
            'ai_interactions': AIResponse.query.filter_by(user_id=s.id).count(),
            'pre_test_score': exp.pre_test_score if exp else None,
            'post_test_score': exp.post_test_score if exp else None,
            'registered': s.created_at.strftime('%Y-%m-%d'),
        })
    return rows


# ================================================================== #
# Private computation helpers
# ================================================================== #

def _compute_mastery(user_id: int, attempts: list) -> float:
    """
    Weighted mastery: recent attempts weighted higher.
    Starts at 0 if no attempts.
    """
    if not attempts:
        return 0.0
    sorted_attempts = sorted(attempts, key=lambda a: a.created_at)
    weights = list(range(1, len(sorted_attempts) + 1))
    weighted_sum = sum(a.score * w for a, w in zip(sorted_attempts, weights))
    total_weight = sum(weights)
    return weighted_sum / total_weight if total_weight > 0 else 0.0


def _compute_weak_topics(user_id: int, attempts: list) -> list:
    """Identify topics where average score < 60%."""
    topic_scores: dict[str, list] = {}
    for attempt in attempts:
        if attempt.quiz and attempt.quiz.lesson:
            topic = attempt.quiz.lesson.topic_category or 'General'
            topic_scores.setdefault(topic, []).append(attempt.score)

    weak = []
    for topic, scores in topic_scores.items():
        if sum(scores) / len(scores) < 60:
            weak.append(topic)
    return weak


def _compute_engagement(user_id: int) -> float:
    """
    Engagement score 0–100 based on:
    - Number of interactions (40%)
    - Session recency (30%)
    - Lesson diversity (30%)
    """
    logs = InteractionLog.query.filter_by(user_id=user_id).all()
    if not logs:
        return 0.0

    interaction_score = min(len(logs) / 100 * 40, 40)

    most_recent = max(log.timestamp for log in logs)
    days_since = (datetime.utcnow() - most_recent).days
    recency_score = max(30 - days_since * 3, 0)

    unique_lessons = len(set(log.lesson_id for log in logs if log.lesson_id))
    diversity_score = min(unique_lessons / 10 * 30, 30)

    return round(interaction_score + recency_score + diversity_score, 2)


def _risk_label(mastery: float, engagement: float) -> str:
    if mastery < 40 or engagement < 20:
        return 'high'
    elif mastery < 65 or engagement < 50:
        return 'medium'
    return 'low'


def _count_high_risk_students() -> int:
    count = 0
    students = User.query.filter_by(role='student').all()
    for s in students:
        attempts = QuizAttempt.query.filter_by(user_id=s.id).all()
        mastery = _compute_mastery(s.id, attempts)
        engagement = _compute_engagement(s.id)
        if _risk_label(mastery, engagement) == 'high':
            count += 1
    return count
