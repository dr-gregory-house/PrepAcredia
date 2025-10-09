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


def test_quiz_detail_page_loads_with_data(client, app):
    """
    GIVEN a logged-in user with a completed quiz in their history
    WHEN they visit the quiz detail page for that quiz
    THEN the page should load successfully and show their results.
    """
    from app.utils.db import get_user_db_connection

    # 1. Create a user and log in
    username = 'quiz_history_user'
    _ensure_user_logged_in(client, app, username)

    # 2. Create mock quiz history data for this user
    with app.app_context():
        conn = get_user_db_connection()
        try:
            user_id = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']

            # Insert a quiz history record
            cursor = conn.cursor()
            cursor.execute('INSERT INTO quiz_history (user_id, score, total_questions) VALUES (?, ?, ?)', (user_id, 1, 1))
            quiz_id = cursor.lastrowid

            # Insert a corresponding answer record (for question id 1, which exists in content DB)
            conn.execute('INSERT INTO quiz_answers (quiz_history_id, question_id, selected_letter, is_correct) VALUES (?, ?, ?, ?)',
                         (quiz_id, 1, 'A', 1))
            conn.commit()
        finally:
            conn.close()

    # 3. Visit the quiz detail page
    # This request will trigger the bug in the `quiz_detail` route
    resp = client.get(f'/profile/quiz/{quiz_id}')

    # 4. Assert that the page loads correctly (this will fail before the fix)
    assert resp.status_code == 200
    assert b'Quiz Details' in resp.data
    assert b'Question 1' in resp.data # Check for some expected content
