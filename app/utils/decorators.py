from functools import wraps
from flask import session, redirect, url_for, flash, request
from app.utils.db import get_db_connection

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        user_id = session['user_id']
        conn = get_db_connection()
        user = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user or user['role'] != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('main.home'))
        
        return f(*args, **kwargs)
    return decorated_function 