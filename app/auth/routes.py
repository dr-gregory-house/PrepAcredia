from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.utils.db import get_db_connection

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
            error = 'Please provide username and password'
    
    return render_template('auth/login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
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
            existing_email = conn.execute('SELECT 1 FROM users WHERE email = ?', (email,)).fetchone()
            existing_username = conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
            
            if existing_email:
                conn.close()
                error = 'Email already registered'
            elif existing_username:
                conn.close()
                error = 'Username already taken'
            else:
                # In a real app, you would hash the password
                # For now, we'll store it directly (not secure!)
                conn.execute(
                    'INSERT INTO users (username, email, name, password_hash, is_active) VALUES (?, ?, ?, ?, ?)',
                    (username, email, name, password, 1)
                )
                conn.commit()
                
                # Get the newly created user
                user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
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