def test_register_login_logout_flow(client, app):
    # Register a new user (is_active defaults to 0, so we cannot login yet)
    resp = client.post('/auth/register', data={
        'email': 'u1@example.com',
        'username': 'u1',
        'name': 'User One',
        'password': 'pass'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'pending activation' in resp.data.lower()

    # Manually activate user in user.db
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            conn.execute('UPDATE users SET is_active = 1 WHERE username = ?', ('u1',))
            conn.commit()
        finally:
            conn.close()

    # Login should now work
    resp = client.post('/auth/login', data={'username': 'u1', 'password': 'pass'}, follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' not in resp.headers.get('Location', '')  # should redirect to home

    # Logout should clear session
    resp = client.get('/auth/logout', follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' in resp.headers.get('Location', '')


