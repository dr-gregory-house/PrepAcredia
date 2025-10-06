def _make_admin_active(app, username='admin_test'):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            # Ensure admin user exists and is active
            row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active) VALUES (?, ?, ?, ?, ?)', (username, f'{username}@example.com', 'Admin T', 'admin', 1))
                conn.commit()
            else:
                conn.execute('UPDATE users SET role = "admin", is_active = 1 WHERE username = ?', (username,))
                conn.commit()
        finally:
            conn.close()


def _login(client, app, username):
    # Bypass password check by ensuring password_hash is set
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            conn.execute('UPDATE users SET password_hash = "x" WHERE username = ?', (username,))
            conn.commit()
        finally:
            conn.close()
    return client.post('/auth/login', data={'username': username, 'password': 'x'}, follow_redirects=False)


def test_admin_requires_auth_and_admin_role(client, app):
    # Without login
    resp = client.get('/admin/', follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' in resp.headers.get('Location', '')

    # Login as normal user
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', ('u2', 'u2@example.com', 'User Two', 'user', 1, 'x'))
            conn.commit()
        finally:
            conn.close()
    client.post('/auth/login', data={'username': 'u2', 'password': 'x'})
    resp = client.get('/admin/', follow_redirects=False)
    # Should redirect away due to lack of admin role
    assert resp.status_code in (301, 302, 303, 307, 308)

    # Elevate to admin and access
    _make_admin_active(app, 'u2')
    _login(client, app, 'u2')
    resp = client.get('/admin/', follow_redirects=True)
    assert resp.status_code == 200


def test_admin_settings_schedule_preview_and_update(client, app):
    _make_admin_active(app, 'u3')
    _login(client, app, 'u3')

    # Access settings
    resp = client.get('/admin/settings')
    assert resp.status_code == 200

    # Preview schedule
    resp = client.post('/admin/settings/spaced_repetition/preview', data={'schedule_type': 'faster'})
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert 'schedule' in data and 'total_days' in data

    # Update schedule to slower
    resp = client.post('/admin/settings/spaced_repetition', data={'schedule_type': 'slower'}, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Review schedule updated' in resp.data


