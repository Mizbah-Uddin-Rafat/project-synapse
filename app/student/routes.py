"""
MODULES 2, 3, 5 — Student Routes
===================================
Dashboard, lessons, quiz submission, behaviour tracking, recommendations.
"""

import json
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import (db, Course, Lesson, Quiz, Question, QuizAttempt,
                      StudentProgress, InteractionLog, Recommendation)
from ..analytics.analytics_service import get_student_summary, get_progress_over_time, get_topic_performance
from .recommendation_service import generate_recommendations

student_bp = Blueprint('student', __name__)


# ------------------------------------------------------------------ #
# Dashboard
# ------------------------------------------------------------------ #

@student_bp.route('/dashboard')
@login_required
def dashboard():
    """Student home — mastery, progress, recommendations."""
    summary = get_student_summary(current_user.id)
    recommendations = (
        Recommendation.query
        .filter_by(user_id=current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(5).all()
    )
    recent_ai = (
        from_ai_history := __import__(
            'app.models', fromlist=['AIResponse']
        ).AIResponse.query.filter_by(user_id=current_user.id)
        .order_by(__import__('app.models', fromlist=['AIResponse']).AIResponse.timestamp.desc())
        .limit(3).all()
    )
    courses = Course.query.all()

    return render_template(
        'student/dashboard.html',
        summary=summary,
        recommendations=recommendations,
        ai_history=recent_ai,
        courses=courses,
    )


# ------------------------------------------------------------------ #
# Courses & Lessons
# ------------------------------------------------------------------ #

@student_bp.route('/courses')
@login_required
def courses():
    all_courses = Course.query.all()
    return render_template('student/courses.html', courses=all_courses)


@student_bp.route('/lesson/<int:lesson_id>')
@login_required
def lesson(lesson_id):
    """View a lesson — logs open event automatically."""
    lesson_obj = Lesson.query.get_or_404(lesson_id)

    # Track lesson open
    _log_event(current_user.id, lesson_id, 'lesson_open')

    # Upsert progress record
    progress = StudentProgress.query.filter_by(
        user_id=current_user.id, lesson_id=lesson_id
    ).first()
    if not progress:
        progress = StudentProgress(user_id=current_user.id, lesson_id=lesson_id)
        db.session.add(progress)
    progress.last_accessed = datetime.utcnow()
    db.session.commit()

    quizzes = Quiz.query.filter_by(lesson_id=lesson_id).all()
    return render_template(
        'student/lesson.html',
        lesson=lesson_obj,
        quizzes=quizzes,
        progress=progress,
    )


@student_bp.route('/lesson/<int:lesson_id>/complete', methods=['POST'])
@login_required
def complete_lesson(lesson_id):
    """Mark a lesson as completed and update progress."""
    data = request.get_json()
    time_spent = data.get('time_spent', 0)
    clicks = data.get('clicks', 0)

    progress = StudentProgress.query.filter_by(
        user_id=current_user.id, lesson_id=lesson_id
    ).first()
    if progress:
        progress.completed = True
        progress.completion_percentage = 100.0
        db.session.commit()

    _log_event(current_user.id, lesson_id, 'lesson_close',
               duration=time_spent, clicks=clicks)

    return jsonify({'success': True})


# ------------------------------------------------------------------ #
# Quiz
# ------------------------------------------------------------------ #

@student_bp.route('/quiz/<int:quiz_id>')
@login_required
def quiz(quiz_id):
    """Render quiz page."""
    quiz_obj = Quiz.query.get_or_404(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).all()

    _log_event(current_user.id, quiz_obj.lesson_id, 'quiz_start')

    attempt_count = QuizAttempt.query.filter_by(
        user_id=current_user.id, quiz_id=quiz_id
    ).count()

    return render_template(
        'student/quiz.html',
        quiz=quiz_obj,
        questions=questions,
        attempt_number=attempt_count + 1,
    )


@student_bp.route('/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    """
    Process quiz submission.
    Saves attempt, logs event, then triggers ML prediction + recommendations.
    """
    quiz_obj = Quiz.query.get_or_404(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).all()

    data = request.get_json()
    answers = data.get('answers', {})  # {question_id: selected_option}
    time_taken = data.get('time_taken', 0)

    # Score the attempt
    correct = 0
    wrong = 0
    for q in questions:
        given = answers.get(str(q.id), '').upper()
        if given == q.correct_answer.upper():
            correct += 1
        else:
            wrong += 1

    score = (correct / len(questions) * 100) if questions else 0.0

    attempt_count = QuizAttempt.query.filter_by(
        user_id=current_user.id, quiz_id=quiz_id
    ).count()

    attempt = QuizAttempt(
        user_id=current_user.id,
        quiz_id=quiz_id,
        score=score,
        total_questions=len(questions),
        correct_answers=correct,
        wrong_answers=wrong,
        time_taken=time_taken,
        attempt_number=attempt_count + 1,
        answers_json=json.dumps(answers),
    )
    db.session.add(attempt)

    # Update lesson progress mastery
    if quiz_obj.lesson_id:
        progress = StudentProgress.query.filter_by(
            user_id=current_user.id, lesson_id=quiz_obj.lesson_id
        ).first()
        if progress:
            progress.mastery_score = score

    db.session.commit()

    # Log quiz submission event
    _log_event(current_user.id, quiz_obj.lesson_id, 'quiz_submit',
               duration=time_taken, response_time=time_taken / max(len(questions), 1))

    # Generate recommendations based on result
    try:
        from ..analytics.analytics_service import get_student_summary
        summary = get_student_summary(current_user.id)
        generate_recommendations(
            user_id=current_user.id,
            mastery_score=summary['mastery_score'],
            weak_topics=summary['weak_topics'],
            risk_level='high' if summary['mastery_score'] < 40 else 'low',
            current_lesson_id=quiz_obj.lesson_id,
        )
    except Exception:
        pass  # Recommendations are best-effort — don't fail the submission

    # Trigger ML prediction
    try:
        from ..student.ml_predict import predict_student
        predict_student(current_user.id)
    except Exception:
        pass

    return jsonify({
        'success': True,
        'score': round(score, 1),
        'correct': correct,
        'wrong': wrong,
        'total': len(questions),
    })


# ------------------------------------------------------------------ #
# Behaviour Tracking API (called by JS)
# ------------------------------------------------------------------ #

@student_bp.route('/track', methods=['POST'])
@login_required
def track_event():
    """
    Generic event tracking endpoint.
    Called by the frontend JavaScript tracker.
    """
    data = request.get_json()
    _log_event(
        user_id=current_user.id,
        lesson_id=data.get('lesson_id'),
        action_type=data.get('action_type', 'click'),
        duration=data.get('duration', 0),
        clicks=data.get('clicks', 0),
        response_time=data.get('response_time', 0.0),
        metadata=data.get('metadata'),
    )
    return jsonify({'success': True})


# ------------------------------------------------------------------ #
# Recommendations
# ------------------------------------------------------------------ #

@student_bp.route('/recommendations')
@login_required
def recommendations():
    recs = (
        Recommendation.query
        .filter_by(user_id=current_user.id)
        .order_by(Recommendation.created_at.desc())
        .limit(20).all()
    )
    return render_template('student/recommendations.html', recommendations=recs)


# ------------------------------------------------------------------ #
# Private helpers
# ------------------------------------------------------------------ #

def _log_event(user_id, lesson_id, action_type, duration=0,
               clicks=0, response_time=0.0, metadata=None):
    """Persist a single interaction event."""
    import json as _json
    log = InteractionLog(
        user_id=user_id,
        lesson_id=lesson_id,
        action_type=action_type,
        duration=duration,
        clicks=clicks,
        response_time=response_time,
        metadata_json=_json.dumps(metadata) if metadata else None,
    )
    db.session.add(log)
    db.session.commit()
