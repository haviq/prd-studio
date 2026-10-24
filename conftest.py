import os
import sys
import tempfile

# Must be set before auth/server import: they read env at module load.
os.environ['AUTH_DB'] = os.path.join(tempfile.gettempdir(), 'prd_test_%d.db' % os.getpid())
os.environ['ADMIN_SECRET'] = 'test-admin-secret'
os.environ['SESSION_SECRET'] = 'test-session-secret'
os.environ['AI_API_KEY'] = ''  # no real AI calls in tests
os.environ['PAKASIR_SLUG'] = 'test-slug'  # checkout tests
os.environ['PRICE_PRO'] = '49000'
os.environ['FREE_LIMIT'] = '1'  # quota-defer test: a single allowed generate

sys.path.insert(0, os.path.dirname(__file__))

import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app, base_url='https://testserver')


@pytest.fixture()
def signed_up():
    """A fresh user with session cookie; returns email."""
    email = 'u%s@test.dev' % os.urandom(4).hex()
    r = client.post('/api/signup', json={'email': email, 'password': 'secret123'})
    assert r.status_code == 200, r.text
    return email


@pytest.fixture()
def admin_headers():
    return {'X-Admin-Code': 'test-admin-secret'}
