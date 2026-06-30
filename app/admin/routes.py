"""
MODULE 7B — Admin / Research Dashboard Routes
==============================================
Admin-only views: platform overview, student management,
A/B experiment analysis, course management.
"""

from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import (db, User, Course, Lesson, Quiz, Question,
                      InteractionLog, ExperimentResult)
from ..analytics.analytics_service import (
    get_platform_overview, get_all_students_summary,
    get_ab_experiment_stats, get_student_summary,
)

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------ #
# Main Dashboard
# ------------------------------------------------------------------ #

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    overview = get_platform_overview()
    students = get_all_students_summary()
    ab_stats = get_ab_experiment_stats()
    return render_template(
        'admin/dashboard.html',
        overview=overview,
        students=students,
        ab_stats=ab_stats,
    )


# ------------------------------------------------------------------ #
# Student Detail
# ------------------------------------------------------------------ #

@admin_bp.route('/student/<int:student_id>')
@login_required
@admin_required
def student_detail(student_id):
    student = User.query.get_or_404(student_id)
    summary = get_student_summary(student_id)
    logs = InteractionLog.query.filter_by(user_id=student_id)\
        .order_by(InteractionLog.timestamp.desc()).limit(50).all()
    return render_template(
        'admin/student_detail.html',
        student=student,
        summary=summary,
        logs=logs,
    )


# ------------------------------------------------------------------ #
# Course Management
# ------------------------------------------------------------------ #

@admin_bp.route('/courses')
@login_required
@admin_required
def courses():
    all_courses = Course.query.all()
    return render_template('admin/courses.html', courses=all_courses)


@admin_bp.route('/courses/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_course():
    if request.method == 'POST':
        course = Course(
            title=request.form['title'],
            description=request.form.get('description', ''),
            category=request.form.get('category', ''),
            difficulty=request.form.get('difficulty', 'beginner'),
        )
        db.session.add(course)
        db.session.commit()
        flash('Course created!', 'success')
        return redirect(url_for('admin.courses'))
    return render_template('admin/course_form.html', course=None)


@admin_bp.route('/lessons/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_lesson():
    courses = Course.query.all()
    if request.method == 'POST':
        lesson = Lesson(
            course_id=int(request.form['course_id']),
            title=request.form['title'],
            content=request.form.get('content', ''),
            video_url=request.form.get('video_url', ''),
            topic_category=request.form.get('topic_category', ''),
            difficulty=request.form.get('difficulty', 'beginner'),
            order_index=int(request.form.get('order_index', 0)),
        )
        db.session.add(lesson)
        db.session.commit()
        flash('Lesson created!', 'success')
        return redirect(url_for('admin.courses'))
    return render_template('admin/lesson_form.html', courses=courses)


@admin_bp.route('/questions/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_question():
    from ..models import Quiz, Lesson
    # Load quizzes with their lesson names for the dropdown
    quizzes = db.session.query(Quiz).join(Lesson).all()
    if request.method == 'POST':
        q = Question(
            quiz_id=int(request.form['quiz_id']),
            question_text=request.form['question_text'],
            option_a=request.form['option_a'],
            option_b=request.form['option_b'],
            option_c=request.form['option_c'],
            option_d=request.form['option_d'],
            correct_answer=request.form['correct_answer'].upper(),
            topic_tag=request.form.get('topic_tag', ''),
            difficulty=request.form.get('difficulty', 'medium')
        )
        db.session.add(q)
        db.session.commit()
        flash(f'Question added! Add another or go back to courses.', 'success')
        return redirect(url_for('admin.new_question'))
    return render_template('admin/question_form.html', quizzes=quizzes)


# ------------------------------------------------------------------ #
# Experiment Management
# ------------------------------------------------------------------ #

@admin_bp.route('/experiment/record', methods=['POST'])
@login_required
@admin_required
def record_experiment():
    """Record pre/post test scores for a student's experiment entry."""
    data = request.get_json()
    student = User.query.get_or_404(data['user_id'])

    exp = ExperimentResult.query.filter_by(user_id=student.id).first()
    if not exp:
        exp = ExperimentResult(user_id=student.id, group_type=student.group_type)
        db.session.add(exp)

    exp.pre_test_score = data.get('pre_test_score', exp.pre_test_score or 0)
    exp.post_test_score = data.get('post_test_score', exp.post_test_score or 0)
    db.session.commit()
    return jsonify({'success': True})
