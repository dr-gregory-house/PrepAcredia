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


def test_get_never_attempted_count_logic(client, app):
    """
    GIVEN a user who has answered some questions
    WHEN the get_never_attempted_count function is called
    THEN it should return the total number of questions minus the number of unique questions answered by the user.
    """
    from app.utils.analytics import get_never_attempted_count
    from app.utils.db import get_user_db_connection, get_content_db_connection

    with app.app_context():
        # 1. Setup a user
        username = 'never_attempted_user'
        _ensure_user_logged_in(client, app, username)

        user_conn = get_user_db_connection()
        user_id = user_conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']

        # 2. Get total questions from content DB
        content_conn = get_content_db_connection()
        total_questions = content_conn.execute('SELECT COUNT(id) FROM questions').fetchone()[0]
        content_conn.close()

        # 3. Simulate user answering 2 unique questions
        cursor = user_conn.cursor()
        cursor.execute('INSERT INTO quiz_history (user_id, score, total_questions) VALUES (?, ?, ?)', (user_id, 2, 2))
        quiz_history_id = cursor.lastrowid
        # Assuming question IDs 1 and 2 exist in content.db
        cursor.execute('INSERT INTO quiz_answers (quiz_history_id, question_id, selected_letter, is_correct) VALUES (?, ?, ?, ?)',
                         (quiz_history_id, 1, 'A', 1))
        cursor.execute('INSERT INTO quiz_answers (quiz_history_id, question_id, selected_letter, is_correct) VALUES (?, ?, ?, ?)',
                         (quiz_history_id, 2, 'B', 1))
        user_conn.commit()

        # 4. Call the function and assert the correct count
        # The buggy version will return 0, so this will fail.
        never_attempted = get_never_attempted_count(user_id)

        # There are 5 questions in the content DB seed. User has seen 2.
        assert never_attempted == total_questions - 2

        user_conn.close()
