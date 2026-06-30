"""
MODULE 1 — Authentication Routes
=================================
Handles registration, login, logout, and session management.
"""

import random
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from ..models import db, User
from .forms import RegistrationForm, LoginForm

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Student/admin registration with automatic A/B group assignment."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data,
            email=form.email.data,
            role=form.role.data,
            # Random 50/50 A/B group assignment — key for research validity
            group_type=random.choice(['control', 'experimental'])
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash(f'Account created! You have been assigned to the {user.group_type} group.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login with role-based redirect."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if user.role == 'admin':
                return redirect(next_page or url_for('admin.dashboard'))
            return redirect(next_page or url_for('student.dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout and clear session."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
