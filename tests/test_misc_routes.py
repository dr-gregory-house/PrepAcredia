def _ensure_active_user(app, username='misc_user'):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', (username, f'{username}@example.com', 'Misc User', 'user', 1, 'x'))
                conn.commit()
        finally:
            conn.close()


def test_get_tags_returns_empty_dict(client, app):
    _ensure_active_user(app)
    client.post('/auth/login', data={'username': 'misc_user', 'password': 'x'})
    resp = client.post('/get_tags')
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json() == {'tags': {}}


def test_pending_activation_page_renders(client):
    resp = client.get('/auth/pending_activation')
    assert resp.status_code == 200
    # Basic smoke check for HTML
    assert b'pending' in resp.data.lower() or b'activation' in resp.data.lower()


