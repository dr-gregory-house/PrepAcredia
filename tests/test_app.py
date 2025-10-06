def test_app_factory_creates_app(app):
    assert app is not None
    assert app.testing is True


def test_root_redirects_to_login_when_not_authenticated(client):
    resp = client.get('/', follow_redirects=False)
    # Expect a redirect to /auth/login
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert '/auth/login' in resp.headers.get('Location', '')


def test_auth_login_page_renders(client):
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    assert b'Login' in resp.data or b'username' in resp.data


