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


def rate_check(key, limit, window):
    """DB-backed sliding-window rate limit. Returns True if allowed.
    Survives container restarts, unlike an in-memory counter."""
    if limit <= 0:
        return True
    now = time.time()
    con = _db()
    try:
        con.execute('DELETE FROM rate_limits WHERE key=? AND ts < ?', (key, now - window))
        n = con.execute('SELECT COUNT(*) c FROM rate_limits WHERE key=?', (key,)).fetchone()['c']
        if n >= limit:
            con.commit()
            return False
        con.execute('INSERT INTO rate_limits(key, ts) VALUES(?, ?)', (key, now))
        con.commit()
        return True
    finally:
        con.close()


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
    CREATE TABLE IF NOT EXISTS rate_limits(
        key TEXT, ts REAL
    );
    CREATE INDEX IF NOT EXISTS idx_rate_key ON rate_limits(key);
    ''')
    for stmt in (
        "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE projects ADD COLUMN revisions INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ai_provider TEXT",
        "ALTER TABLE users ADD COLUMN ai_base_url TEXT",
        "ALTER TABLE users ADD COLUMN ai_key TEXT",
        "ALTER TABLE users ADD COLUMN ai_model TEXT",
        "ALTER TABLE users ADD COLUMN password TEXT",
        "ALTER TABLE projects ADD COLUMN share_id TEXT",
        "ALTER TABLE projects ADD COLUMN shared INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN lang TEXT DEFAULT 'en'",
    ):
        try:
            con.execute(stmt)
        except Exception:
            pass
    con.commit(); con.close()


def hash_password(pw):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 120000).hex()
    return salt + '$' + h


def verify_password(pw, stored):
    if not stored or '$' not in stored:
        return False
    salt, h = stored.split('$', 1)
    calc = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 120000).hex()
    return hmac.compare_digest(calc, h)


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


@router.post('/api/login')
async def api_login(request: Request):
    """Email + password login for manually-created accounts (no GitHub)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    email = (body.get('email') or '').strip().lower()
    pw = body.get('password') or ''
    if not email or not pw:
        raise HTTPException(400, 'email and password required')
    con = _db()
    row = con.execute('SELECT * FROM users WHERE lower(email)=?', (email,)).fetchone()
    con.close()
    if not row or not verify_password(pw, row['password']):
        raise HTTPException(401, 'wrong email or password')
    resp = JSONResponse({'ok': True, 'login': row['login']})
    resp.set_cookie('prd_session', sign(str(row['id'])), httponly=True, secure=True,
                    samesite='lax', path='/', max_age=60 * 60 * 24 * 30)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@router.post('/api/signup')
async def api_signup(request: Request):
    """Public email + password signup."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    email = (body.get('email') or '').strip().lower()
    pw = body.get('password') or ''
    name = (body.get('name') or '').strip()
    if not email or '@' not in email or '.' not in email:
        raise HTTPException(400, 'valid email required')
    if len(pw) < 6:
        raise HTTPException(400, 'password must be at least 6 characters')
    login = email.split('@')[0][:30]
    con = _db()
    if con.execute('SELECT id FROM users WHERE lower(email)=?', (email,)).fetchone():
        con.close()
        raise HTTPException(409, 'email already registered')
    base = login
    n = 1
    while con.execute('SELECT id FROM users WHERE login=?', (login,)).fetchone():
        n += 1
        login = base + str(n)
    cur = con.execute('INSERT INTO users(github_id, login, name, email, plan, password) VALUES(?,?,?,?,?,?)',
                      ('email:' + email, login, name or login, email, 'free', hash_password(pw)))
    con.commit()
    uid = cur.lastrowid
    con.close()
    resp = JSONResponse({'ok': True, 'login': login})
    resp.set_cookie('prd_session', sign(str(uid)), httponly=True, secure=True,
                    samesite='lax', path='/', max_age=60 * 60 * 24 * 30)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@router.post('/api/admin/set-password')
async def api_admin_set_password(request: Request):
    _require_admin(request)
    body = await request.json()
    uid = int(body.get('user_id') or 0)
    pw = (body.get('password') or '').strip()
    if len(pw) < 6:
        raise HTTPException(400, 'password must be at least 6 characters')
    con = _db()
    con.execute('UPDATE users SET password=? WHERE id=?', (hash_password(pw), uid))
    con.commit(); con.close()
    return {'ok': True, 'user_id': uid}


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


PAKASIR_SLUG = os.environ.get('PAKASIR_SLUG', 'kasss')
PAKASIR_API_KEY = os.environ.get('PAKASIR_API_KEY', '')
PAKASIR_WEBHOOK_SECRET = os.environ.get('PAKASIR_WEBHOOK_SECRET', '')
PAKASIR_API = 'https://app.pakasir.com/api/v2'
PRICE_PRO = int(os.environ.get('PRICE_PRO', '49000'))


def _ensure_orders(con):
    con.execute('''CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY, user_id INTEGER, plan TEXT, status TEXT, txn_id TEXT,
        amount INTEGER, method TEXT, created_at TEXT DEFAULT (datetime('now')))''')
    for col in ('txn_id TEXT', 'amount INTEGER', 'method TEXT'):
        try:
            con.execute('ALTER TABLE orders ADD COLUMN ' + col)
        except Exception:
            pass


@router.post('/api/checkout')
async def api_checkout(request: Request):
    """Create a real Pakasir transaction and return the payment link."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    plan = body.get('plan', 'pro')
    method = (body.get('method') or 'qris').strip()
    amount = int(body.get('amount') or PRICE_PRO)
    order = 'PRD' + secrets.token_hex(6).upper()
    con = _db()
    _ensure_orders(con)
    con.execute('INSERT INTO orders(id,user_id,plan,status,amount,method) VALUES(?,?,?,?,?,?)',
                (order, u['id'], plan, 'pending', amount, method))
    con.commit(); con.close()

    if not PAKASIR_API_KEY:
        return {'order': order, 'plan': plan, 'status': 'pending', 'configured': False,
                'detail': 'Pakasir API key not set on the server yet.',
                'pay_url': 'https://app.pakasir.com/pay/' + PAKASIR_SLUG + '/' + str(amount) + '?order_id=' + order}
    try:
        r = httpx.post(PAKASIR_API + '/create-transaction/' + PAKASIR_SLUG + '/' + order,
                       headers={'X-Api-Key': PAKASIR_API_KEY, 'Content-Type': 'application/json'},
                       json={'method': method, 'amount': amount}, timeout=20)
        data = r.json()
    except Exception as e:
        raise HTTPException(502, 'payment gateway error: ' + str(e))
    pay_url = (data.get('payment_link') or data.get('url') or
               data.get('checkout_url') or data.get('redirect_url'))
    txn = data.get('txn_id') or ''
    if txn:
        con = _db()
        con.execute('UPDATE orders SET txn_id=? WHERE id=?', (txn, order))
        con.commit(); con.close()
    if not pay_url:
        pay_url = 'https://app.pakasir.com/pay/' + PAKASIR_SLUG + '/' + str(amount) + '?order_id=' + order
    return {'order': order, 'plan': plan, 'status': 'pending', 'txn_id': txn,
            'amount': amount, 'method': method, 'pay_url': pay_url}


@router.post('/api/pakasir/notify')
async def api_pakasir_notify(request: Request):
    """Webhook from Pakasir. Verifies the secret header, marks the order paid
    and upgrades the user to Pro."""
    secret = request.headers.get('X-Secret', '')
    if PAKASIR_WEBHOOK_SECRET and secret != PAKASIR_WEBHOOK_SECRET:
        raise HTTPException(403, 'invalid secret')
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    order = str(body.get('order_id') or '')
    status = str(body.get('status') or '')
    if not order:
        raise HTTPException(400, 'order_id required')
    con = _db()
    _ensure_orders(con)
    row = con.execute('SELECT * FROM orders WHERE id=?', (order,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'order not found')
    if status == 'completed':
        con.execute("UPDATE orders SET status='paid', txn_id=? WHERE id=?", (body.get('txn_id', ''), order))
        con.execute("UPDATE users SET plan='pro' WHERE id=?", (row['user_id'],))
    elif status == 'canceled':
        con.execute("UPDATE orders SET status='canceled' WHERE id=?", (order,))
    con.commit(); con.close()
    return {'ok': True, 'order': order, 'status': status}


@router.get('/api/checkout/status/{order}')
def api_checkout_status(order: str, request: Request):
    """Poll order status (used by the checkout page after returning from Pakasir)."""
    u = current_user(request)
    con = _db()
    _ensure_orders(con)
    if u:
        row = con.execute('SELECT id,plan,status FROM orders WHERE id=? AND user_id=?', (order, u['id'])).fetchone()
    else:
        row = None
    if not row:
        row = con.execute('SELECT id,plan,status FROM orders WHERE id=?', (order,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, 'order not found')
    return {'order': row['id'], 'plan': row['plan'], 'status': row['status']}


ADMIN_SECRET = os.environ.get('ADMIN_SECRET', '')
ADMIN_PATH = os.environ.get('ADMIN_PATH', '/console-x7f9k2')


def is_admin(request: Request):
    """Admin access is a secret code, not a login. Accepts the code either
    as an X-Admin-Code header or as the signed prd_admin cookie set after
    a successful code entry."""
    code = request.headers.get('X-Admin-Code', '')
    if ADMIN_SECRET and code and hmac.compare_digest(code, ADMIN_SECRET):
        return {'login': 'admin'}
    tok = request.cookies.get('prd_admin')
    if tok and unsign(tok) == 'admin':
        return {'login': 'admin'}
    return None


def _require_admin(request: Request):
    u = is_admin(request)
    if not u:
        raise HTTPException(403, 'admin only')
    return u


@router.post('/api/admin/login')
async def api_admin_login(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    code = (body.get('code') or '').strip()
    if not ADMIN_SECRET or not code or not hmac.compare_digest(code, ADMIN_SECRET):
        raise HTTPException(403, 'invalid code')
    resp = JSONResponse({'ok': True})
    resp.set_cookie('prd_admin', sign('admin'), httponly=True, samesite='lax', max_age=60 * 60 * 24 * 30)
    return resp


@router.post('/api/admin/logout')
def api_admin_logout():
    resp = JSONResponse({'ok': True})
    resp.delete_cookie('prd_admin')
    return resp


@router.get('/api/admin/stats')
def api_admin_stats(request: Request):
    _require_admin(request)
    con = _db()
    _ensure_orders(con)
    users = con.execute('SELECT COUNT(*) c FROM users').fetchone()['c']
    pro = con.execute("SELECT COUNT(*) c FROM users WHERE plan='pro'").fetchone()['c']
    projects = con.execute('SELECT COUNT(*) c FROM projects').fetchone()['c']
    shared = con.execute('SELECT COUNT(*) c FROM projects WHERE shared=1').fetchone()['c']
    gen = con.execute("SELECT COUNT(*) c FROM usage WHERE kind='generate'").fetchone()['c']
    rev = con.execute("SELECT COUNT(*) c FROM usage WHERE kind='revise'").fetchone()['c']
    paid = con.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM orders WHERE status='paid'").fetchone()
    pending = con.execute("SELECT COUNT(*) c FROM orders WHERE status='pending'").fetchone()['c']
    con.close()
    return {'users': users, 'pro': pro, 'projects': projects, 'shared': shared,
            'generates': gen, 'revises': rev,
            'paid_orders': paid['c'], 'revenue': paid['s'], 'pending_orders': pending}


@router.get('/api/admin/users')
def api_admin_users(request: Request):
    _require_admin(request)
    con = _db()
    rows = con.execute('''SELECT u.id, u.login, u.name, u.email, u.plan, u.created_at,
        (SELECT COUNT(*) FROM projects p WHERE p.user_id=u.id) projects,
        (SELECT COUNT(*) FROM usage x WHERE x.user_id=u.id) actions
        FROM users u ORDER BY u.id DESC LIMIT 200''').fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.get('/api/admin/orders')
def api_admin_orders(request: Request):
    _require_admin(request)
    con = _db()
    _ensure_orders(con)
    rows = con.execute('''SELECT o.id, o.plan, o.status, o.amount, o.method, o.txn_id,
        o.created_at, u.login FROM orders o LEFT JOIN users u ON u.id=o.user_id
        ORDER BY o.created_at DESC LIMIT 200''').fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post('/api/admin/set-plan')
async def api_admin_set_plan(request: Request):
    _require_admin(request)
    body = await request.json()
    uid = int(body.get('user_id') or 0)
    plan = (body.get('plan') or 'free').strip()
    if plan not in ('free', 'pro'):
        raise HTTPException(400, 'plan must be free or pro')
    con = _db()
    con.execute('UPDATE users SET plan=? WHERE id=?', (plan, uid))
    con.commit(); con.close()
    return {'ok': True, 'user_id': uid, 'plan': plan}


@router.get('/api/admin/whoami')
def api_admin_whoami(request: Request):
    u = is_admin(request)
    return {'admin': bool(u), 'login': (u.get('login') if u else None)}


@router.post('/api/admin/users/create')
async def api_admin_create_user(request: Request):
    _require_admin(request)
    body = await request.json()
    login = (body.get('login') or '').strip()
    if not login:
        raise HTTPException(400, 'login required')
    con = _db()
    exists = con.execute('SELECT id FROM users WHERE login=?', (login,)).fetchone()
    if exists:
        con.close()
        raise HTTPException(409, 'login already exists')
    pw = (body.get('password') or '').strip()
    cur = con.execute('INSERT INTO users(github_id, login, name, email, plan, password) VALUES(?,?,?,?,?,?)',
                      ('manual:' + login, login, (body.get('name') or login).strip(),
                       (body.get('email') or '').strip(), (body.get('plan') or 'free'),
                       (hash_password(pw) if len(pw) >= 6 else None)))
    con.commit()
    uid = cur.lastrowid
    con.close()
    return {'ok': True, 'id': uid, 'login': login}


@router.post('/api/admin/users/delete')
async def api_admin_delete_user(request: Request):
    _require_admin(request)
    body = await request.json()
    uid = int(body.get('user_id') or 0)
    con = _db()
    row = con.execute('SELECT id, login FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'user not found')
    con.execute('DELETE FROM projects WHERE user_id=?', (uid,))
    con.execute('DELETE FROM usage WHERE user_id=?', (uid,))
    con.execute('DELETE FROM users WHERE id=?', (uid,))
    con.commit(); con.close()
    return {'ok': True, 'deleted': uid, 'login': row['login']}


@router.get('/api/admin/timeseries')
def api_admin_timeseries(request: Request, days: int = 14):
    """Daily signups, generates and revenue for the last N days."""
    _require_admin(request)
    days = max(1, min(90, days))
    con = _db()
    _ensure_orders(con)
    signups = {r['d']: r['c'] for r in con.execute(
        "SELECT date(created_at) d, COUNT(*) c FROM users WHERE created_at >= date('now', ?) GROUP BY d", ('-%d day' % days,)).fetchall()}
    gens = {r['d']: r['c'] for r in con.execute(
        "SELECT date(created_at) d, COUNT(*) c FROM usage WHERE kind='generate' AND created_at >= date('now', ?) GROUP BY d", ('-%d day' % days,)).fetchall()}
    rev = {r['d']: r['s'] for r in con.execute(
        "SELECT date(created_at) d, COALESCE(SUM(amount),0) s FROM orders WHERE status='paid' AND created_at >= date('now', ?) GROUP BY d", ('-%d day' % days,)).fetchall()}
    con.close()
    import datetime as _dt
    today = _dt.date.today()
    series = []
    for i in range(days - 1, -1, -1):
        d = (today - _dt.timedelta(days=i)).isoformat()
        series.append({'date': d, 'signups': signups.get(d, 0),
                       'generates': gens.get(d, 0), 'revenue': rev.get(d, 0)})
    return {'days': days, 'series': series}


@router.get('/api/admin/recent')
def api_admin_recent(request: Request):
    """Recent activity feed for the admin overview."""
    _require_admin(request)
    con = _db()
    _ensure_orders(con)
    users = [dict(r) for r in con.execute(
        'SELECT login, name, plan, created_at FROM users ORDER BY id DESC LIMIT 8').fetchall()]
    orders = [dict(r) for r in con.execute(
        '''SELECT o.id, o.status, o.amount, o.method, o.created_at, u.login
           FROM orders o LEFT JOIN users u ON u.id=o.user_id
           ORDER BY o.created_at DESC LIMIT 8''').fetchall()]
    acts = [dict(r) for r in con.execute(
        '''SELECT x.kind, x.name, x.created_at, u.login FROM usage x
           LEFT JOIN users u ON u.id=x.user_id ORDER BY x.id DESC LIMIT 12''').fetchall()]
    con.close()
    return {'users': users, 'orders': orders, 'activity': acts}


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
    row = con.execute('SELECT id, name, template, markdown, lang, created_at FROM projects WHERE share_id=? AND shared=1', (sid,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, 'not found')
    return dict(row)


@router.post('/api/shared/{sid}/translate')
async def api_shared_translate(sid: str, request: Request):
    """Return a shared PRD in another language. Cached per language so repeat
    views are instant; generated on demand the first time."""
    body = await request.json()
    want = (body.get('lang') or 'en').strip()
    if want not in ('en', 'id'):
        raise HTTPException(400, 'unsupported language')
    con = _db()
    con.executescript('''CREATE TABLE IF NOT EXISTS shared_cache(
        share_id TEXT, lang TEXT, markdown TEXT, created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY(share_id, lang));''')
    row = con.execute('SELECT name, template, payload, markdown, lang FROM projects WHERE share_id=? AND shared=1', (sid,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'not found')
    if want == (row['lang'] or 'en'):
        con.close()
        return {'markdown': row['markdown'], 'lang': want, 'cached': True}
    cached = con.execute('SELECT markdown FROM shared_cache WHERE share_id=? AND lang=?', (sid, want)).fetchone()
    if cached:
        con.close()
        return {'markdown': cached['markdown'], 'lang': want, 'cached': True}
    con.close()

    import server as _server
    payload = {}
    try:
        payload = json.loads(row['payload'] or '{}')
    except Exception:
        payload = {}
    req = _server.GenReq(
        name=row['name'],
        description=payload.get('description', '') or row['name'],
        features=payload.get('features', ''),
        users=payload.get('users', ''),
        tech=payload.get('tech', ''),
        template=row['template'] or 'Web App',
        lang=want)
    md = _server._gen_prd(req, None)
    con = _db()
    con.execute('INSERT OR REPLACE INTO shared_cache(share_id,lang,markdown) VALUES(?,?,?)', (sid, want, md))
    con.commit(); con.close()
    return {'markdown': md, 'lang': want, 'cached': False}
