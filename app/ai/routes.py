import traceback
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from ..models import Lesson, AIResponse
from ..analytics.analytics_service import get_student_summary
from . import ai_service

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/explain', methods=['POST'])
@login_required
def explain():
    data = request.get_json()
    topic = data.get('topic', '')
    lesson_id = data.get('lesson_id')
    summary = get_student_summary(current_user.id)
    lesson_content = ''
    if lesson_id:
        lesson = Lesson.query.get(lesson_id)
        if lesson:
            lesson_content = lesson.content or ''
    try:
        response = ai_service.generate_explanation(
            user_id=current_user.id,
            topic=topic,
            weak_topics=summary.get('weak_topics', []),
            mastery_score=summary.get('mastery_score', 50.0),
            lesson_content=lesson_content,
        )
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        print("=" * 70)
        print("ERROR IN /ai/explain:")
        traceback.print_exc()
        print("=" * 70)
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/summary', methods=['POST'])
@login_required
def summarise():
    data = request.get_json()
    lesson_id = data.get('lesson_id')
    lesson = Lesson.query.get_or_404(lesson_id)
    summary = get_student_summary(current_user.id)
    try:
        response = ai_service.generate_summary(
            user_id=current_user.id,
            lesson_title=lesson.title,
            lesson_content=lesson.content or '',
            mastery_score=summary.get('mastery_score', 50.0),
            weak_topics=summary.get('weak_topics', []),
        )
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        print("=" * 70)
        print("ERROR IN /ai/summary:")
        traceback.print_exc()
        print("=" * 70)
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/generate-quiz', methods=['POST'])
@login_required
def generate_quiz():
    data = request.get_json()
    topic = data.get('topic', 'General Knowledge')
    summary = get_student_summary(current_user.id)
    try:
        questions = ai_service.generate_quiz(
            user_id=current_user.id,
            topic=topic,
            weak_topics=summary.get('weak_topics', []),
            mastery_score=summary.get('mastery_score', 50.0),
        )
        return jsonify({'success': True, 'questions': questions})
    except Exception as e:
        print("=" * 70)
        print("ERROR IN /ai/generate-quiz:")
        traceback.print_exc()
        print("=" * 70)
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/revision-notes', methods=['POST'])
@login_required
def revision_notes():
    data = request.get_json()
    course_title = data.get('course_title', 'Your Course')
    summary = get_student_summary(current_user.id)
    try:
        response = ai_service.generate_revision_notes(
            user_id=current_user.id,
            course_title=course_title,
            weak_topics=summary.get('weak_topics', []),
            mastery_score=summary.get('mastery_score', 50.0),
        )
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        print("=" * 70)
        print("ERROR IN /ai/revision-notes:")
        traceback.print_exc()
        print("=" * 70)
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/history')
@login_required
def history():
    responses = (
        AIResponse.query
        .filter_by(user_id=current_user.id)
        .order_by(AIResponse.timestamp.desc())
        .limit(50).all()
    )
    return render_template('student/ai_history.html', responses=responses)