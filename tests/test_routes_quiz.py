def test_quiz_routes_require_login(client):
    # Accessing quiz pages without login should redirect to login
    resp = client.get('/quiz/', follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' in resp.headers.get('Location', '')


