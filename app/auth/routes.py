from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.utils.db import get_db_connection
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# User authentication routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('main.home'))
    
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if email and password:
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE email = ? AND password_hash IS NOT NULL', (email,)).fetchone()
            conn.close()
            
            if user and user['is_active']:
                # In a real app, you would verify the password hash here
                # For now, we'll just simulate a successful login
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_role'] = user['role']
                flash('Login successful!', 'success')
                
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('main.home'))
            else:
                error = 'Invalid credentials or account deactivated'
        else:
            error = 'Please provide email and password'
    
    return render_template('auth/login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('main.home'))
    
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        
        if email and name and password:
            conn = get_db_connection()
            existing_user = conn.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone()
            
            if existing_user:
                conn.close()
                error = 'Email already registered'
            else:
                # In a real app, you would hash the password
                # For now, we'll store it directly (not secure!)
                conn.execute(
                    'INSERT INTO users (email, name, password_hash, is_active) VALUES (?, ?, ?, ?)',
                    (email, name, password, 1)
                )
                conn.commit()
                
                # Get the newly created user
                user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
                conn.close()
                
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_role'] = user['role']
                
                flash('Registration successful!', 'success')
                return redirect(url_for('main.home'))
        else:
            error = 'Please fill out all fields'
    
    return render_template('auth/register.html', error=error)

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_role', None)
    return redirect(url_for('main.home'))

# Google OAuth routes
@auth_bp.route('/google')
def login_google():
    oauth = current_app.extensions['authlib.integrations.flask_client']
    redirect_uri = url_for('auth.authorized', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/google/authorized')
def authorized():
    oauth = current_app.extensions['authlib.integrations.flask_client']
    try:
        token = oauth.google.authorize_access_token()
        # Fix the userinfo URL
        resp = oauth.google.get('https://www.googleapis.com/oauth2/v2/userinfo')
        user_info = resp.json()
        
        # Check if user exists with this Google ID
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE google_id = ?', (user_info['id'],)).fetchone()
        
        if not user:
            # Create new user
            conn.execute(
                'INSERT INTO users (email, name, google_id, profile_picture, is_active) VALUES (?, ?, ?, ?, ?)',
                (user_info['email'], user_info['name'], user_info['id'], user_info.get('picture', ''), 1)
            )
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE google_id = ?', (user_info['id'],)).fetchone()
        elif not user['is_active']:
            conn.close()
            flash('Your account has been deactivated', 'error')
            return redirect(url_for('auth.login'))
        
        conn.close()
        
        # Set user session
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        
        return redirect(url_for('main.home'))
    except Exception as e:
        print(f"OAuth error: {str(e)}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('auth.login')) 