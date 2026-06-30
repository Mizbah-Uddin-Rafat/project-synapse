"""
Admin Routes — Fixed version
Adds: quiz creation endpoint, quiz_id prefill on question form,
      save-and-add-another support.
"""

from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import (db, User, Course, Lesson, Quiz, Question,
                      InteractionLog, ExperimentResult)
from ..analytics.analytics_service import (
    get_platform_overview, get_all_students_summary,
    get_ab_experiment_stats, get_student_summary)

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
# Dashboard
# ------------------------------------------------------------------ #
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    overview = get_platform_overview()
    students = get_all_students_summary()
    ab_stats = get_ab_experiment_stats()
    return render_template('admin/dashboard.html',
                           overview=overview,
                           students=students,
                           ab_stats=ab_stats)


# ------------------------------------------------------------------ #
# Student Detail
# ------------------------------------------------------------------ #
@admin_bp.route('/student/<int:student_id>')
@login_required
@admin_required
def student_detail(student_id):
    student = User.query.get_or_404(student_id)
    summary = get_student_summary(student_id)
    logs = (InteractionLog.query.filter_by(user_id=student_id)
            .order_by(InteractionLog.timestamp.desc()).limit(50).all())
    return render_template('admin/student_detail.html',
                           student=student, summary=summary, logs=logs)


# ------------------------------------------------------------------ #
# Courses
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
        flash(f'Course "{course.title}" created successfully!', 'success')
        return redirect(url_for('admin.courses'))
    return render_template('admin/course_form.html', course=None)


# ------------------------------------------------------------------ #
# Lessons
# ------------------------------------------------------------------ #
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

        # Auto-create a quiz for this lesson
        quiz = Quiz(
            lesson_id=lesson.id,
            title=f'{lesson.title} Quiz',
            description=f'Assessment quiz for {lesson.title}',
        )
        db.session.add(quiz)
        db.session.commit()

        flash(f'Lesson "{lesson.title}" and its quiz created! Now add questions.', 'success')
        # Redirect straight to add question for this quiz
        return redirect(url_for('admin.new_question', quiz_id=quiz.id))

    return render_template('admin/lesson_form.html', courses=courses)


# ------------------------------------------------------------------ #
# Quiz — create via AJAX (called from courses page)
# ------------------------------------------------------------------ #
@admin_bp.route('/quiz/create', methods=['POST'])
@login_required
@admin_required
def create_quiz():
    data = request.get_json()
    lesson_id = data.get('lesson_id')
    title     = data.get('title', 'Quiz')

    if not lesson_id:
        return jsonify({'success': False, 'error': 'lesson_id required'})

    lesson = Lesson.query.get(lesson_id)
    if not lesson:
        return jsonify({'success': False, 'error': 'Lesson not found'})

    quiz = Quiz(lesson_id=lesson_id, title=title,
                description=f'Assessment for {lesson.title}')
    db.session.add(quiz)
    db.session.commit()
    return jsonify({'success': True, 'quiz_id': quiz.id})


# ------------------------------------------------------------------ #
# Questions — with quiz_id prefill support
# ------------------------------------------------------------------ #
@admin_bp.route('/questions/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_question():
    quizzes = Quiz.query.all()

    # Pre-select quiz if quiz_id passed in URL e.g. ?quiz_id=3
    prefill_quiz_id = request.args.get('quiz_id', type=int)
    selected_quiz   = Quiz.query.get(prefill_quiz_id) if prefill_quiz_id else None

    if request.method == 'POST':
        quiz_id        = int(request.form['quiz_id'])
        action         = request.form.get('action', 'save')

        q = Question(
            quiz_id=quiz_id,
            question_text=request.form['question_text'],
            option_a=request.form['option_a'],
            option_b=request.form['option_b'],
            option_c=request.form['option_c'],
            option_d=request.form['option_d'],
            correct_answer=request.form['correct_answer'].upper(),
            topic_tag=request.form.get('topic_tag', ''),
            difficulty=request.form.get('difficulty', 'medium'),
        )
        db.session.add(q)
        db.session.commit()

        flash('Question added successfully!', 'success')

        # Save and add another — stay on the form with same quiz pre-selected
        if action == 'save_add_another':
            return redirect(url_for('admin.new_question', quiz_id=quiz_id))

        return redirect(url_for('admin.courses'))

    return render_template('admin/question_form.html',
                           quizzes=quizzes,
                           selected_quiz=selected_quiz)


# ------------------------------------------------------------------ #
# Experiment recording
# ------------------------------------------------------------------ #
@admin_bp.route('/experiment/record', methods=['POST'])
@login_required
@admin_required
def record_experiment():
    data    = request.get_json()
    student = User.query.get_or_404(data['user_id'])
    exp     = ExperimentResult.query.filter_by(user_id=student.id).first()
    if not exp:
        exp = ExperimentResult(user_id=student.id, group_type=student.group_type)
        db.session.add(exp)
    exp.pre_test_score  = data.get('pre_test_score',  exp.pre_test_score  or 0)
    exp.post_test_score = data.get('post_test_score', exp.post_test_score or 0)
    db.session.commit()
    return jsonify({'success': True})
