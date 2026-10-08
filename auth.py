"""GitHub OAuth, sessions and project storage for PRD Studio."""
import os, json, time, hmac, hashlib, secrets, sqlite3
from pathlib import Path
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
import httpx

GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')
SESSION_SECRET = os.environ.get('SESSION_SECRET', '') or secrets.token_hex(32)
PUBLIC_URL = os.environ.get('PUBLIC_URL', 'https://prd.haaviq.dev').rstrip('/')
DB_PATH = os.environ.get('AUTH_DB', '/app/data/prd.db')

router = APIRouter()


def _db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = _db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id TEXT UNIQUE, login TEXT, name TEXT, avatar TEXT, email TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, template TEXT,
        payload TEXT, markdown TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    ''')
    con.commit(); con.close()


def sign(value):
    mac = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value + '.' + mac


def unsign(token):
    if not token or '.' not in token:
        return None
    value, mac = token.rsplit('.', 1)
    expect = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(mac, expect):
        return value
    return None


def current_user(request: Request):
    token = request.cookies.get('prd_session')
    uid = unsign(token) if token else None
    if not uid:
        return None
    con = _db()
    row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    con.close()
    return dict(row) if row else None


def _base(request):
    """Build the public base URL from the actual request, so the OAuth
    redirect always matches the domain the visitor is using."""
    if PUBLIC_URL:
        return PUBLIC_URL
    proto = request.headers.get('x-forwarded-proto', 'https').split(',')[0].strip()
    host = request.headers.get('host') or request.url.netloc
    return proto + '://' + host


@router.get('/auth/github')
def auth_github(request: Request):
    if not GITHUB_CLIENT_ID:
        raise HTTPException(500, 'GitHub OAuth not configured')
    state = secrets.token_urlsafe(16)
    redirect_uri = _base(request) + '/auth/github/callback'
    q = urlencode({'client_id': GITHUB_CLIENT_ID, 'redirect_uri': redirect_uri,
                   'scope': 'read:user user:email', 'state': state})
    resp = RedirectResponse('https://github.com/login/oauth/authorize?' + q)
    resp.set_cookie('prd_state', sign(state), httponly=True, secure=True, samesite='lax', max_age=600)
    return resp


@router.get('/auth/github/callback')
def auth_callback(request: Request, code: str = '', state: str = ''):
    saved = unsign(request.cookies.get('prd_state', ''))
    if not code or not state or state != saved:
        return RedirectResponse('/studio?auth=error')
    try:
        tok = httpx.post('https://github.com/login/oauth/access_token',
                         headers={'Accept': 'application/json'},
                         data={'client_id': GITHUB_CLIENT_ID, 'client_secret': GITHUB_CLIENT_SECRET,
                               'code': code, 'redirect_uri': PUBLIC_URL + '/auth/github/callback'},
                         timeout=20).json()
        access = tok.get('access_token')
        if not access:
            return RedirectResponse('/studio?auth=error')
        h = {'Authorization': 'Bearer ' + access, 'Accept': 'application/vnd.github+json'}
        gh = httpx.get('https://api.github.com/user', headers=h, timeout=20).json()
        email = gh.get('email') or ''
        if not email:
            try:
                emails = httpx.get('https://api.github.com/user/emails', headers=h, timeout=20).json()
                primary = [e for e in emails if e.get('primary')]
                email = (primary[0]['email'] if primary else (emails[0]['email'] if emails else ''))
            except Exception:
                email = ''
    except Exception:
        return RedirectResponse('/studio?auth=error')

    con = _db()
    con.execute('''INSERT INTO users(github_id,login,name,avatar,email) VALUES(?,?,?,?,?)
                   ON CONFLICT(github_id) DO UPDATE SET login=excluded.login,name=excluded.name,
                   avatar=excluded.avatar,email=excluded.email''',
                (str(gh.get('id')), gh.get('login'), gh.get('name') or gh.get('login'),
                 gh.get('avatar_url'), email))
    con.commit()
    row = con.execute('SELECT id FROM users WHERE github_id=?', (str(gh.get('id')),)).fetchone()
    con.close()

    resp = RedirectResponse('/studio?auth=ok')
    resp.set_cookie('prd_session', sign(str(row['id'])), httponly=True, secure=True, samesite='lax', max_age=60 * 60 * 24 * 30)
    resp.delete_cookie('prd_state')
    return resp


@router.post('/auth/logout')
def auth_logout():
    resp = JSONResponse({'ok': True})
    resp.delete_cookie('prd_session')
    return resp


@router.get('/api/me')
def api_me(request: Request):
    u = current_user(request)
    if not u:
        return {'logged_in': False, 'oauth': bool(GITHUB_CLIENT_ID)}
    return {'logged_in': True, 'login': u['login'], 'name': u['name'], 'avatar': u['avatar'], 'email': u['email']}


@router.get('/api/projects')
def api_projects(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    rows = con.execute('SELECT id,name,template,created_at FROM projects WHERE user_id=? ORDER BY id DESC LIMIT 100',
                       (u['id'],)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.get('/api/projects/{pid}')
def api_project(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    row = con.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, u['id'])).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, 'not found')
    return dict(row)


@router.post('/api/projects')
async def api_save(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    name = (body.get('name') or '').strip()
    markdown = body.get('markdown') or ''
    if not name or not markdown:
        raise HTTPException(400, 'name and markdown required')
    con = _db()
    cur = con.execute('INSERT INTO projects(user_id,name,template,payload,markdown) VALUES(?,?,?,?,?)',
                      (u['id'], name, body.get('template', ''), json.dumps(body.get('payload', {})), markdown))
    con.commit()
    pid = cur.lastrowid
    con.close()
    return {'id': pid}


@router.delete('/api/projects/{pid}')
def api_delete(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    con.execute('DELETE FROM projects WHERE id=? AND user_id=?', (pid, u['id']))
    con.commit(); con.close()
    return {'ok': True}
