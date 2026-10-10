"""GitHub OAuth, sessions and project storage for PRD Studio."""
import os, json, time, hmac, hashlib, secrets, sqlite3
from pathlib import Path
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
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
    CREATE TABLE IF NOT EXISTS usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, kind TEXT, name TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    ''')
    for stmt in (
        "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE projects ADD COLUMN revisions INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ai_provider TEXT",
        "ALTER TABLE users ADD COLUMN ai_base_url TEXT",
        "ALTER TABLE users ADD COLUMN ai_key TEXT",
        "ALTER TABLE users ADD COLUMN ai_model TEXT",
        "ALTER TABLE projects ADD COLUMN share_id TEXT",
        "ALTER TABLE projects ADD COLUMN shared INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN lang TEXT DEFAULT 'en'",
    ):
        try:
            con.execute(stmt)
        except Exception:
            pass
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
    # Self-verifying state: signed, no cookie needed (survives cross-site redirect).
    # No redirect_uri sent: GitHub uses the callback registered on the OAuth app,
    # which avoids redirect_uri_mismatch entirely.
    state = sign(secrets.token_urlsafe(16))
    q = urlencode({'client_id': GITHUB_CLIENT_ID,
                   'scope': 'read:user user:email', 'state': state})
    return RedirectResponse('https://github.com/login/oauth/authorize?' + q)


@router.get('/auth/github/callback')
def auth_callback(request: Request, code: str = '', state: str = ''):
    if not code or not state or not unsign(state):
        print('[oauth] bad state/code: code=%s state=%s' % (bool(code), bool(state)), flush=True)
        return RedirectResponse('/studio?auth=error&r=state')
    try:
        tok = httpx.post('https://github.com/login/oauth/access_token',
                         headers={'Accept': 'application/json'},
                         data={'client_id': GITHUB_CLIENT_ID, 'client_secret': GITHUB_CLIENT_SECRET,
                               'code': code},
                         timeout=20).json()
        access = tok.get('access_token')
        if not access:
            print('[oauth] token exchange failed: %s' % (tok,), flush=True)
            return RedirectResponse('/studio?auth=error&r=token')
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
    resp.set_cookie('prd_session', sign(str(row['id'])), httponly=True, secure=True,
                    samesite='lax', path='/', max_age=60 * 60 * 24 * 30)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@router.post('/auth/logout')
def auth_logout():
    resp = JSONResponse({'ok': True})
    resp.delete_cookie('prd_session')
    return resp


def log_usage(user, kind, name=''):
    """Record a usage event for a signed-in user (no-op for guests)."""
    if not user:
        return
    try:
        con = _db()
        con.execute('INSERT INTO usage(user_id,kind,name) VALUES(?,?,?)', (user['id'], kind, name))
        con.commit(); con.close()
    except Exception:
        pass


@router.get('/api/usage')
def api_usage(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    rows = con.execute("SELECT kind, COUNT(*) c FROM usage WHERE user_id=? GROUP BY kind", (u['id'],)).fetchall()
    totals = {r['kind']: r['c'] for r in rows}
    today = con.execute("SELECT COUNT(*) c FROM usage WHERE user_id=? AND date(created_at)=date('now')", (u['id'],)).fetchone()['c']
    recent = con.execute('SELECT kind,name,created_at FROM usage WHERE user_id=? ORDER BY id DESC LIMIT 25', (u['id'],)).fetchall()
    proj = con.execute('SELECT COUNT(*) c FROM projects WHERE user_id=?', (u['id'],)).fetchone()['c']
    con.close()
    return {'plan': u.get('plan') or 'free', 'today': today, 'totals': totals,
            'projects': proj, 'recent': [dict(r) for r in recent]}


@router.get('/api/ai-settings')
def api_ai_settings(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    key = u.get('ai_key') or ''
    return {
        'provider': u.get('ai_provider') or '',
        'base_url': u.get('ai_base_url') or '',
        'model': u.get('ai_model') or '',
        'has_key': bool(key),
        'key_hint': (key[:6] + '...' + key[-4:]) if len(key) > 12 else ('set' if key else ''),
    }


class AISettingsReq(BaseModel):
    provider: str = ''
    base_url: str = ''
    model: str = ''
    api_key: str = ''


@router.post('/api/ai-settings')
def api_ai_settings_save(req: AISettingsReq, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    if req.api_key == '':
        con.execute('UPDATE users SET ai_provider=?, ai_base_url=?, ai_model=? WHERE id=?',
                    (req.provider, req.base_url, req.model, u['id']))
    else:
        con.execute('UPDATE users SET ai_provider=?, ai_base_url=?, ai_model=?, ai_key=? WHERE id=?',
                    (req.provider, req.base_url, req.model, req.api_key, u['id']))
    con.commit(); con.close()
    return {'ok': True}


@router.post('/api/ai-settings/clear')
def api_ai_settings_clear(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    con.execute("UPDATE users SET ai_provider='', ai_base_url='', ai_model='', ai_key='' WHERE id=?", (u['id'],))
    con.commit(); con.close()
    return {'ok': True}


def user_ai_config(user):
    """Return a signed-in user's custom AI config, or None to use the default."""
    if not user:
        return None
    key = user.get('ai_key') or ''
    base = user.get('ai_base_url') or ''
    if not key and not base:
        return None
    return {'provider': (user.get('ai_provider') or 'openai').lower(),
            'base_url': base, 'api_key': key, 'model': user.get('ai_model') or ''}


@router.get('/api/me')
def api_me(request: Request):
    u = current_user(request)
    if not u:
        print('[me] no session. cookies=%s' % (list(request.cookies.keys()),), flush=True)
        return {'logged_in': False, 'oauth': bool(GITHUB_CLIENT_ID)}
    return {'logged_in': True, 'login': u['login'], 'name': u['name'],
            'avatar': u['avatar'], 'email': u['email'], 'plan': u.get('plan') or 'free'}


@router.post('/api/checkout')
async def api_checkout(request: Request):
    """Mock checkout. Creates a pending order and returns a fake pay URL.
    Replace the body with a real gateway (Stripe / LemonSqueezy / Midtrans):
    create a checkout session, then set plan='pro' in the webhook handler."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    plan = body.get('plan', 'pro')
    order = 'ord_' + secrets.token_hex(8)
    con = _db()
    con.execute('CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, user_id INTEGER, plan TEXT, status TEXT, created_at TEXT DEFAULT (datetime(\'now\')))')
    con.execute('INSERT INTO orders(id,user_id,plan,status) VALUES(?,?,?,?)', (order, u['id'], plan, 'pending'))
    con.commit(); con.close()
    return {'order': order, 'plan': plan, 'status': 'pending',
            'pay_url': '/checkout?order=' + order}


@router.post('/api/checkout/confirm')
async def api_checkout_confirm(request: Request):
    """Mock payment confirmation. A real gateway would call this from a webhook
    after the payment succeeds. Here we simply mark the order paid and upgrade."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    order = body.get('order', '')
    con = _db()
    row = con.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (order, u['id'])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'order not found')
    con.execute("UPDATE orders SET status='paid' WHERE id=?", (order,))
    con.execute("UPDATE users SET plan='pro' WHERE id=?", (u['id'],))
    con.commit(); con.close()
    return {'ok': True, 'plan': 'pro', 'message': 'Upgraded to Pro (demo). No real payment was taken.'}


@router.post('/api/subscribe')
async def api_subscribe(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    return {'status': 'use_checkout', 'plan': u.get('plan') or 'free'}


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
    cur = con.execute('INSERT INTO projects(user_id,name,template,payload,markdown,lang) VALUES(?,?,?,?,?,?)',
                      (u['id'], name, body.get('template', ''), json.dumps(body.get('payload', {})), markdown, body.get('lang', 'en')))
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


@router.post('/api/projects/{pid}/share')
def api_share(pid: int, request: Request):
    """Toggle public sharing for a project. Returns the public share id."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    row = con.execute('SELECT share_id, shared, lang FROM projects WHERE id=? AND user_id=?', (pid, u['id'])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'not found')
    if row['shared']:
        con.execute('UPDATE projects SET shared=0 WHERE id=?', (pid,))
        con.commit(); con.close()
        return {'shared': False}
    sid = row['share_id'] or secrets.token_urlsafe(8)
    con.execute('UPDATE projects SET shared=1, share_id=? WHERE id=?', (sid, pid))
    con.commit(); con.close()
    lang = row['lang'] or 'en'
    return {'shared': True, 'share_id': sid, 'lang': lang, 'url': '/p/' + sid + '/' + lang}


@router.get('/api/shared/{sid}')
def api_shared(sid: str, request: Request):
    """Public read-only view of a shared project. No auth required."""
    con = _db()
    row = con.execute('SELECT name, template, markdown, lang, created_at FROM projects WHERE share_id=? AND shared=1', (sid,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, 'not found')
    return dict(row)
