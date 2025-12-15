from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, g
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from app.utils.db import get_user_db_connection
from app.utils.user_tracking import create_user_session, end_user_session, log_user_activity
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.urls import url_parse
import sys

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField('Password', validators=[DataRequired()])

# User authentication routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('main.home'))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        conn = get_user_db_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

            if user and user['password_hash'] and check_password_hash(user['password_hash'], password):
                if not user['is_active']:
                    flash('Your account is pending activation. Please contact the administrator.', 'warning')
                    return redirect(url_for('auth.pending_activation'))

                # Create user session and store token
                session_token = create_user_session(user['id'])
                session['session_token'] = session_token

                # Store user info in session
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_role'] = user['role']

                # Set session to be secure and httpOnly
                session.permanent = True
                session.modified = True

                # Log the login activity
                log_user_activity(user['id'], 'login', f'User logged in from {request.remote_addr}')

                flash('Login successful!', 'success')

                next_page = request.args.get('next')
                if not next_page or url_parse(next_page).netloc != '':
                    next_page = url_for('main.home')
                return redirect(next_page)
            else:
                flash('Invalid credentials', 'error')
        finally:
            conn.close()

    return render_template('auth/login.html', form=form)

class RegisterForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    name = StringField('Full Name', validators=[DataRequired(), Length(min=1, max=100)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('main.home'))

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()  # Normalize email
        username = form.username.data.strip()  # Sanitize username
        name = form.name.data.strip()  # Sanitize name
        password = form.password.data

        conn = get_user_db_connection()
        try:
            # Check for existing users with case-insensitive email/username
            existing_email = conn.execute('SELECT 1 FROM users WHERE LOWER(email) = ?', (email,)).fetchone()
            existing_username = conn.execute('SELECT 1 FROM users WHERE LOWER(username) = ?', (username.lower(),)).fetchone()

            if existing_email:
                flash('Email already registered', 'error')
            elif existing_username:
                flash('Username already taken', 'error')
            else:
                # Hash the password before storing
                hashed_password = generate_password_hash(password)

                # Set is_active to 0 by default
                conn.execute(
                    'INSERT INTO users (username, email, name, password_hash, is_active) VALUES (?, ?, ?, ?, ?)',
                    (username, email, name, hashed_password, 0)
                )
                conn.commit()

                # Mark as significant database change (user registration)
                g.significant_db_change = True

                flash('Registration successful! Your account is pending activation. Please contact the administrator.', 'info')
                return redirect(url_for('auth.pending_activation'))
        except Exception as e:
            conn.rollback()
            flash(f'Registration error: {str(e)}', 'error')
        finally:
            conn.close()

    return render_template('auth/register.html', form=form)

@auth_bp.route('/pending_activation')
def pending_activation():
    return render_template('auth/pending_activation.html')

@auth_bp.route('/logout')
def logout():
    if 'session_token' in session:
        # End the user session
        end_user_session(session['session_token'])
        
        # Log the logout activity
        if 'user_id' in session:
            log_user_activity(session['user_id'], 'logout', f'User logged out from {request.remote_addr}')
    
    # Clear session data
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
