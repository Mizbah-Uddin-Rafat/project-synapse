"""
MODULE 7 — Analytics Routes
=============================
Provides JSON endpoints consumed by Chart.js dashboards,
plus CSV export for research analysis.
"""

import csv
import io
from flask import Blueprint, jsonify, make_response, request
from flask_login import login_required, current_user
from functools import wraps
from .analytics_service import (
    get_student_summary, get_progress_over_time, get_topic_performance,
    get_platform_overview, get_all_students_summary, get_ab_experiment_stats,
    get_engagement_trend, export_experiment_csv_data,
)

analytics_bp = Blueprint('analytics', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


# ================================================================== #
# STUDENT ANALYTICS ENDPOINTS
# ================================================================== #

@analytics_bp.route('/student/summary')
@login_required
def student_summary():
    """Full analytics summary for the logged-in student."""
    data = get_student_summary(current_user.id)
    return jsonify(data)


@analytics_bp.route('/student/progress')
@login_required
def student_progress():
    """Score-over-time data for the progress line chart."""
    data = get_progress_over_time(current_user.id)
    return jsonify(data)


@analytics_bp.route('/student/topics')
@login_required
def student_topics():
    """Per-topic performance for radar chart."""
    data = get_topic_performance(current_user.id)
    return jsonify(data)


# ================================================================== #
# ADMIN ANALYTICS ENDPOINTS
# ================================================================== #

@analytics_bp.route('/admin/overview')
@login_required
@admin_required
def admin_overview():
    """Platform-wide statistics."""
    return jsonify(get_platform_overview())


@analytics_bp.route('/admin/students')
@login_required
@admin_required
def admin_students():
    """All students summary table."""
    return jsonify(get_all_students_summary())


@analytics_bp.route('/admin/ab-test')
@login_required
@admin_required
def ab_test_stats():
    """A/B experiment group comparison."""
    return jsonify(get_ab_experiment_stats())


@analytics_bp.route('/admin/engagement-trend')
@login_required
@admin_required
def engagement_trend():
    """Daily active users for the last 30 days."""
    days = request.args.get('days', 30, type=int)
    return jsonify(get_engagement_trend(days))


# ================================================================== #
# DATA EXPORT
# ================================================================== #

@analytics_bp.route('/admin/export/csv')
@login_required
@admin_required
def export_csv():
    """
    Export full experiment dataset as CSV.
    Suitable for SPSS, R, or Python statistical analysis.
    """
    rows = export_experiment_csv_data()
    if not rows:
        return jsonify({'error': 'No data to export'}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=synapse_experiment_data.csv'
    return response
