from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.utils.db import get_db_connection
from app.utils.user_tracking import create_user_session, end_user_session, log_user_activity
import sys

# Import global variable for tracking database changes
# This will be shared with app.py
try:
    from app.app import db_changed
except ImportError:
    # Fallback if not available directly
    db_changed = None

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# User authentication routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('main.home'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE username = ? AND password_hash IS NOT NULL', (username,)).fetchone()
            conn.close()
            
            if user:
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
                
                # Log the login activity
                log_user_activity(user['id'], 'login', f'User logged in from {request.remote_addr}')
                
                flash('Login successful!', 'success')
                
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('main.home'))
            else:
                error = 'Invalid credentials'
        else:
            error = 'Please provide username and password'
    
    return render_template('auth/login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    global db_changed  # Access the global variable
    
    if 'user_id' in session:
        return redirect(url_for('main.home'))
    
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        
        if email and username and name and password:
            conn = get_db_connection()
            try:
                existing_email = conn.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone()
                existing_username = conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
                
                if existing_email:
                    error = 'Email already registered'
                elif existing_username:
                    error = 'Username already taken'
                else:
                    # Set is_active to 0 by default
                    conn.execute(
                        'INSERT INTO users (username, email, name, password_hash, is_active) VALUES (?, ?, ?, ?, ?)',
                        (username, email, name, password, 0)
                    )
                    conn.commit()
                    
                    # Explicitly mark database as changed
                    if db_changed is not None:
                        db_changed = True
                    
                    flash('Registration successful! Your account is pending activation. Please contact the administrator.', 'info')
                    return redirect(url_for('auth.pending_activation'))
            except Exception as e:
                conn.rollback()
                error = f'Registration error: {str(e)}'
            finally:
                conn.close()
        else:
            error = 'Please fill out all fields'
    
    return render_template('auth/register.html', error=error)

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