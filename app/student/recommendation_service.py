"""
MODULE 5 — Adaptive Recommendation Engine
==========================================
Rule-based first, then ML-augmented suggestions.

Logic hierarchy:
1. If mastery < 50%    → recommend beginner / revision content
2. If repeated failures → recommend targeted revision
3. If mastery > 80%   → recommend advanced content
4. Default            → recommend next sequential lesson
"""

from datetime import datetime
from ..models import db, Lesson, StudentProgress, QuizAttempt, Recommendation


def generate_recommendations(user_id: int, mastery_score: float,
                              weak_topics: list, risk_level: str,
                              current_lesson_id: int = None) -> list:
    """
    Main entry point — generate and persist recommendations for a student.
    Returns list of Recommendation objects.
    """
    recommendations = []

    # ------------------------------------------------------------------ #
    # Rule 1 — High risk / low mastery → revision material
    # ------------------------------------------------------------------ #
    if mastery_score < 50 or risk_level == 'high':
        lesson = _find_lesson_by_topic(weak_topics, difficulty='beginner',
                                       exclude_id=current_lesson_id)
        if lesson:
            rec = _make_recommendation(
                user_id=user_id,
                rec_type='revision',
                content=lesson.title,
                lesson_id=lesson.id,
                reason=(f'Your mastery score is {mastery_score:.1f}%. '
                        f'Revising beginner material on {", ".join(weak_topics)} '
                        'will strengthen your foundation.'),
                mastery=mastery_score,
            )
            recommendations.append(rec)

    # ------------------------------------------------------------------ #
    # Rule 2 — Repeated failures on same topic → targeted revision
    # ------------------------------------------------------------------ #
    struggling_topic = _detect_repeated_failures(user_id)
    if struggling_topic:
        lesson = _find_lesson_by_topic([struggling_topic], difficulty='beginner',
                                       exclude_id=current_lesson_id)
        if lesson:
            rec = _make_recommendation(
                user_id=user_id,
                rec_type='easier',
                content=lesson.title,
                lesson_id=lesson.id,
                reason=(f'You have had multiple failures on {struggling_topic}. '
                        'This easier lesson will help you build confidence.'),
                mastery=mastery_score,
            )
            recommendations.append(rec)

    # ------------------------------------------------------------------ #
    # Rule 3 — High mastery → advanced content
    # ------------------------------------------------------------------ #
    if mastery_score >= 80 and risk_level == 'low':
        lesson = _find_lesson_by_topic([], difficulty='advanced',
                                       exclude_id=current_lesson_id)
        if lesson:
            rec = _make_recommendation(
                user_id=user_id,
                rec_type='advanced',
                content=lesson.title,
                lesson_id=lesson.id,
                reason=(f'Excellent work! Your mastery is {mastery_score:.1f}%. '
                        'You are ready for advanced material.'),
                mastery=mastery_score,
            )
            recommendations.append(rec)

    # ------------------------------------------------------------------ #
    # Rule 4 — Default: next lesson in sequence
    # ------------------------------------------------------------------ #
    if current_lesson_id:
        next_lesson = _get_next_lesson(user_id, current_lesson_id)
        if next_lesson:
            rec = _make_recommendation(
                user_id=user_id,
                rec_type='next_lesson',
                content=next_lesson.title,
                lesson_id=next_lesson.id,
                reason='Continue your learning journey with the next lesson.',
                mastery=mastery_score,
            )
            recommendations.append(rec)

    # ------------------------------------------------------------------ #
    # Rule 5 — Always suggest AI practice exercises
    # ------------------------------------------------------------------ #
    topic = weak_topics[0] if weak_topics else 'General Topics'
    rec = _make_recommendation(
        user_id=user_id,
        rec_type='practice',
        content=f'AI-Generated Practice: {topic}',
        lesson_id=None,
        reason=f'Practice questions on {topic} will reinforce your understanding.',
        mastery=mastery_score,
    )
    recommendations.append(rec)

    return recommendations


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _make_recommendation(user_id, rec_type, content, lesson_id, reason, mastery):
    rec = Recommendation(
        user_id=user_id,
        recommendation_type=rec_type,
        recommended_content=content,
        lesson_id=lesson_id,
        reason=reason,
        mastery_at_time=mastery,
        created_at=datetime.utcnow(),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def _find_lesson_by_topic(topics: list, difficulty: str = 'beginner',
                           exclude_id: int = None) -> Lesson | None:
    """Find a lesson matching topic tags and difficulty."""
    query = Lesson.query.filter_by(difficulty=difficulty)
    if topics:
        from sqlalchemy import or_
        filters = [Lesson.topic_category.ilike(f'%{t}%') for t in topics]
        query = query.filter(or_(*filters))
    if exclude_id:
        query = query.filter(Lesson.id != exclude_id)
    return query.first()


def _detect_repeated_failures(user_id: int) -> str | None:
    """
    Return the topic with 3+ failed attempts in the last 10 quiz attempts.
    Returns None if no such pattern found.
    """
    recent = QuizAttempt.query.filter_by(user_id=user_id)\
        .order_by(QuizAttempt.created_at.desc()).limit(10).all()

    from collections import Counter
    failed_topics = []
    for attempt in recent:
        if attempt.score < 50 and attempt.quiz and attempt.quiz.lesson:
            failed_topics.append(attempt.quiz.lesson.topic_category or 'General')

    counts = Counter(failed_topics)
    for topic, count in counts.most_common(1):
        if count >= 3:
            return topic
    return None


def _get_next_lesson(user_id: int, current_lesson_id: int) -> Lesson | None:
    """Return the next unfinished lesson in the same course."""
    current = Lesson.query.get(current_lesson_id)
    if not current:
        return None

    # Find completed lesson IDs for this student
    completed_ids = {
        p.lesson_id for p in
        StudentProgress.query.filter_by(user_id=user_id, completed=True).all()
    }

    return (
        Lesson.query
        .filter(
            Lesson.course_id == current.course_id,
            Lesson.order_index > current.order_index,
            Lesson.id.notin_(completed_ids),
        )
        .order_by(Lesson.order_index.asc())
        .first()
    )
