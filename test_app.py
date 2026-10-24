"""Enterprise feature tests: auth, projects, API keys, audit, export, RBAC, headers."""
import os

from conftest import client  # noqa: F401  (signed_up / admin_headers are pytest fixtures)


def _rand():
    return os.urandom(4).hex()


def test_health_v2():
    r = client.get('/api/health')
    assert r.status_code == 200
    d = r.json()
    assert d['ok'] is True
    assert 'version' in d


def test_security_headers():
    r = client.get('/api/health')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'DENY'
    assert r.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'


def test_signup_login_me(signed_up):
    r = client.get('/api/me')
    assert r.status_code == 200
    assert r.json()['logged_in'] is True
    assert r.json()['email'] == signed_up


def test_login_wrong_password_is_audited(signed_up, admin_headers):
    r = client.post('/api/login', json={'email': signed_up, 'password': 'wrong!!'})
    assert r.status_code == 401
    r = client.get('/api/admin/audit', headers=admin_headers)
    assert r.status_code == 200
    assert any(a['action'] == 'login_failed' and a['target'] == signed_up for a in r.json())


def test_project_crud_and_share(signed_up):
    r = client.post('/api/projects', json={'name': 'Demo', 'markdown': '# PRD\ncontent'})
    assert r.status_code == 200
    pid = r.json()['id']
    r = client.get('/api/projects')
    assert any(p['name'] == 'Demo' for p in r.json())
    r = client.post('/api/projects/%d/share' % pid)
    assert r.status_code == 200
    sid = r.json()['share_id']
    r = client.get('/api/shared/' + sid)
    assert r.status_code == 200
    assert 'PRD' in r.json()['markdown']
    r = client.delete('/api/projects/%d' % pid)
    assert r.status_code == 200


def test_api_key_lifecycle_and_bearer_auth(signed_up):
    r = client.post('/api/keys', json={'name': 'ci'})
    assert r.status_code == 200
    key = r.json()['api_key']
    assert key.startswith('prd_')

    headers = {'Authorization': 'Bearer ' + key}
    no_cookie = {'prd_session': ''}
    r = client.get('/api/me', headers=headers, cookies=no_cookie)
    assert r.status_code == 200
    assert r.json()['logged_in'] is True

    # key can create a project without a session cookie
    r = client.post('/api/projects', json={'name': 'ViaKey', 'markdown': 'x'},
                    headers=headers, cookies=no_cookie)
    assert r.status_code == 200

    # key list never leaks the full token
    r = client.get('/api/keys')
    assert r.status_code == 200
    assert all(k['prefix'] != key for k in r.json())

    # revoke kills access
    kid = [k for k in r.json() if k['name'] == 'ci'][0]['id']
    r = client.post('/api/keys/%d/revoke' % kid)
    assert r.status_code == 200
    r = client.get('/api/me', headers=headers, cookies=no_cookie)
    assert r.json()['logged_in'] is False


def test_bogus_key_rejected():
    r = client.get('/api/me', headers={'Authorization': 'Bearer prd_deadbeef'},
                   cookies={'prd_session': ''})
    assert r.json()['logged_in'] is False


def test_gdpr_export(signed_up):
    client.post('/api/projects', json={'name': 'ExportMe', 'markdown': '# hi'})
    r = client.get('/api/me/export')
    assert r.status_code == 200
    d = r.json()
    assert d['profile']['email'] == signed_up
    assert any(p['name'] == 'ExportMe' for p in d['projects'])
    assert 'exported_at' in d


def test_team_projects_rbac():
    owner = 'o%s@test.dev' % _rand()
    client.post('/api/signup', json={'email': owner, 'password': 'secret123'})
    r = client.post('/api/teams', json={'name': 'Acme'})
    tid = r.json()['id']

    other = 'v%s@test.dev' % _rand()
    client.post('/api/signup', json={'email': other, 'password': 'secret123'})  # session is now `other`
    r = client.post('/api/login', json={'email': owner, 'password': 'secret123'})  # back to owner
    assert r.status_code == 200

    client.post('/api/teams/%d/invite' % tid, json={'email': other, 'role': 'editor'})
    r = client.post('/api/projects', json={'name': 'TeamProj', 'markdown': 'x'})
    pid = r.json()['id']
    r = client.post('/api/projects/%d/team' % pid, json={'team_id': tid})
    assert r.status_code == 200

    # switch session: log the second user in via the login endpoint
    r = client.post('/api/login', json={'email': other, 'password': 'secret123'})
    assert r.status_code == 200
    r = client.get('/api/teams/%d/projects' % tid)
    assert r.status_code == 200
    assert r.json()['role'] == 'editor'
    assert any(p['name'] == 'TeamProj' for p in r.json()['projects'])

    # a non-member cannot see the team
    third = 'w%s@test.dev' % _rand()
    client.post('/api/signup', json={'email': third, 'password': 'secret123'})
    r = client.get('/api/teams/%d/projects' % tid)
    assert r.status_code == 403


def test_admin_requires_secret():
    r = client.get('/api/admin/stats')
    assert r.status_code == 403
    r = client.get('/api/admin/stats', headers={'X-Admin-Code': 'nope'})
    assert r.status_code == 403


def test_audit_trail_records_actions(signed_up, admin_headers):
    client.post('/api/projects', json={'name': 'Audited', 'markdown': 'x'})
    r = client.get('/api/admin/audit', headers=admin_headers)
    actions = [a['action'] for a in r.json()]
    assert 'project_saved' in actions
    assert 'signup' in actions
