def _ensure_user_logged_in(client, app, username='profile_user'):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', (username, f'{username}@example.com', 'Profile User', 'user', 1, 'x'))
                conn.commit()
        finally:
            conn.close()
    client.post('/auth/login', data={'username': username, 'password': 'x'})


def test_profile_analytics_page_renders(client, app):
    _ensure_user_logged_in(client, app)
    resp = client.get('/profile/analytics')
    assert resp.status_code == 200
    # Basic smoke check for expected sections
    assert b'analytics' in resp.data.lower() or b'stats' in resp.data.lower()


