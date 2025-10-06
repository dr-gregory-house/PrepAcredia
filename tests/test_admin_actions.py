def _ensure_admin_and_user(app, admin_username='admin_actions', user_username='target_user'):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            # Admin
            row = conn.execute('SELECT id FROM users WHERE username = ?', (admin_username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', (admin_username, f'{admin_username}@example.com', 'Admin Actions', 'admin', 1, 'x'))
            else:
                conn.execute('UPDATE users SET role = "admin", is_active = 1, password_hash = "x" WHERE username = ?', (admin_username,))
            # Target user
            row = conn.execute('SELECT id FROM users WHERE username = ?', (user_username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', (user_username, f'{user_username}@example.com', 'Target User', 'user', 1, 'x'))
            conn.commit()
        finally:
            conn.close()


def _login_admin(client, app, username='admin_actions'):
    _ensure_admin_and_user(app, admin_username=username)
    return client.post('/auth/login', data={'username': username, 'password': 'x'})


def _get_user_id(app, username):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            return row['id']
        finally:
            conn.close()


def test_toggle_active_and_admin(client, app):
    _ensure_admin_and_user(app)
    _login_admin(client, app)

    target_id = _get_user_id(app, 'target_user')

    # Toggle active
    resp = client.post(f'/admin/user/{target_id}/toggle_active', follow_redirects=True)
    assert resp.status_code == 200

    # Toggle admin status
    resp = client.post(f'/admin/user/{target_id}/toggle_admin', follow_redirects=True)
    assert resp.status_code == 200


