def _login_user(client, app, username='quiz_user'):
    from app.utils.db import get_user_db_connection
    with app.app_context():
        conn = get_user_db_connection()
        try:
            row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if not row:
                conn.execute('INSERT INTO users (username, email, name, role, is_active, password_hash) VALUES (?,?,?,?,?,?)', (username, f'{username}@example.com', 'Quiz User', 'user', 1, 'x'))
                conn.commit()
        finally:
            conn.close()
    client.post('/auth/login', data={'username': username, 'password': 'x'})


def test_quiz_flow_answer_and_results(client, app):
    _login_user(client, app)

    # Start from home to create quiz selection
    # Home GET renders selection using content DB specialities
    resp = client.get('/')
    assert resp.status_code in (200, 302)  # may redirect or render

    # POST to home to create a quiz with our seeded speciality
    resp = client.post('/', data={
        'specialities': ['General'],
        'num_questions': '1'
    }, follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/quiz/' in resp.headers.get('Location', '')

    # Load quiz page
    resp = client.get('/quiz/', follow_redirects=False)
    assert resp.status_code == 200
    assert b'Custom Quiz' in resp.data

    # Submit an answer to the first question (choose B which is correct in seed)
    # We need the current question id from the page; since templates aren't parsed here,
    # use knowledge of seed (question id = 1) and submit accordingly.
    resp = client.post('/quiz/answer', data={'answer': 'B', 'question_id': '1', 'time_spent': '3'}, follow_redirects=True)
    assert resp.status_code == 200
    assert b'show_answer' in resp.data or b'Next' in resp.data or b'Custom Quiz' in resp.data

    # Move to next question (which completes quiz)
    resp = client.post('/quiz/next', follow_redirects=False)
    # Should redirect to results
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/quiz/results' in resp.headers.get('Location', '')

    # Results page
    resp = client.get('/quiz/results')
    assert resp.status_code == 200
    assert b'Quiz Results' in resp.data


