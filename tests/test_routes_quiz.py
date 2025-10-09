import pytest
from app.utils.db import get_user_db_connection

def test_quiz_routes_require_login(client):
    # Accessing quiz pages without login should redirect to login
    resp = client.get('/quiz/', follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' in resp.headers.get('Location', '')


def test_start_quiz_with_no_undiscovered_questions(client, app):
    """
    GIVEN a logged-in user who has answered all available questions
    WHEN they start a quiz with 'undiscovered only' selected
    THEN it should not crash and should show a flash message.
    """
    # 1. Create and log in as a user
    with app.app_context():
        # Register user
        client.post('/auth/register', data={'email': 'u2@example.com', 'username': 'u2', 'name': 'User Two', 'password': 'password'}, follow_redirects=True)

        # Activate user
        conn = get_user_db_connection()
        user_id = conn.execute('SELECT id FROM users WHERE username = ?', ('u2',)).fetchone()['id']
        conn.execute('UPDATE users SET is_active = 1 WHERE id = ?', (user_id,))
        conn.commit()

        # Log in
        client.post('/auth/login', data={'username': 'u2', 'password': 'password'}, follow_redirects=True)

        # 2. Mark all 'General' questions as answered for this user
        # In the test seed, these are questions 1, 2, and 5.
        hist_cursor = conn.cursor()
        hist_cursor.execute('INSERT INTO quiz_history (user_id, score, total_questions) VALUES (?, ?, ?)', (user_id, 3, 3))
        history_id = hist_cursor.lastrowid

        answered_questions = [(history_id, 1, 'B', 1), (history_id, 2, 'A', 1), (history_id, 5, 'A', 1)]
        conn.executemany('INSERT INTO quiz_answers (quiz_history_id, question_id, selected_letter, is_correct) VALUES (?, ?, ?, ?)', answered_questions)
        conn.commit()
        conn.close()

    # 3. Start a new quiz with 'undiscovered_only'
    # This POST request sets up the session for the quiz
    start_resp = client.post('/', data={
        'specialities': ['General'],
        'num_questions': 1,
        'undiscovered_only': 'on'
    }, follow_redirects=False)

    # We should get a redirect to the quiz page
    assert start_resp.status_code in (301, 302, 303, 307, 308)
    assert '/quiz/' in start_resp.headers.get('Location', '')

    # 4. Access the quiz page, which should trigger the bug (or the fix)
    # The `display_quiz` function is called here.
    quiz_resp = client.get('/quiz/', follow_redirects=True)

    # 5. Assert the outcome
    # After the fix, it should redirect home and show a flash message.
    # The history should show a redirect from /quiz/ to /
    assert len(quiz_resp.history) == 1
    assert quiz_resp.history[0].status_code in (301, 302, 303, 307, 308)
    # The location may be absolute, so we check for the path
    assert quiz_resp.history[0].headers.get('Location').endswith('/')

    # The final page should be the home page
    assert quiz_resp.status_code == 200
    # And it should contain the warning message
    assert b'No undiscovered questions found' in quiz_resp.data
