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


TURSO_URL = os.environ.get('TURSO_DATABASE_URL', '')
TURSO_TOKEN = os.environ.get('TURSO_AUTH_TOKEN', '')
_libsql_client = None


def _turso_client():
    """One sync libsql HTTP-pipeline client per process (the Hrana websocket
    transport was rejected by current Turso cloud; https:// scheme selects
    the HTTP v2 pipeline)."""
    global _libsql_client
    if _libsql_client is None:
        import libsql_client
        url = TURSO_URL
        if url.startswith('libsql://'):
            url = 'https://' + url[len('libsql://'):]
        _libsql_client = libsql_client.create_client_sync(url, auth_token=TURSO_TOKEN)
    return _libsql_client


class _Result:
    """Uniform result object over sqlite3 and libsql cursors: rows are dicts,
    so row['col'], iteration, dict(row) and fetchone/fetchall all work."""

    def __init__(self, rows, lastrowid=None):
        self._rows = rows
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, i):
        return self._rows[i]


class DictConn:
    """Thin wrapper normalizing sqlite3 and libsql connections. Row access is
    by column name, so call sites never care which backend is active."""

    def __init__(self, conn, is_libsql=False):
        self._c = conn
        self._is_libsql = is_libsql

    def _norm(self, cur):
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def execute(self, sql, params=()):
        if self._is_libsql:
            rs = self._c.execute(sql, list(params))
            cols = list(rs.columns or [])
            rows = [dict(zip(cols, row)) for row in rs.rows]
            lastrowid = rows[0]['id'] if (rows and 'id' in cols) else None
            return _Result(rows, lastrowid)
        cur = self._c.execute(sql, params)
        rows = self._norm(cur)
        lastrowid = getattr(cur, 'lastrowid', None)
        return _Result(rows, lastrowid)

    def executemany(self, sql, seq):
        self._c.executemany(sql, seq)
        return None

    def executescript(self, script):
        if self._is_libsql:
            for stmt in [s.strip() for s in script.split(';') if s.strip()]:
                self._c.execute(stmt)
        else:
            self._c.executescript(script)
        return None

    def commit(self):
        # HTTP-pipeline mode autocommits per statement; sqlite3 needs the call
        if not self._is_libsql:
            self._c.commit()

    def close(self):
        # sqlite3 has close(); libsql's Connection has none and HTTP clients
        # are process-cached — both are fine to skip
        if not self._is_libsql:
            try:
                self._c.close()
            except AttributeError:
                pass


def _db():
    """Local sqlite3 by default; Turso (libSQL over HTTP) when
    TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set — used on hosts without a
    persistent disk (Vercel, Render free tier and friends)."""
    if TURSO_URL and TURSO_TOKEN:
        return DictConn(_turso_client(), is_libsql=True)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return DictConn(sqlite3.connect(DB_PATH), is_libsql=False)


def rate_check(key, limit, window, record=True):
    """DB-backed sliding-window rate limit. Returns True if allowed.
    Survives container restarts, unlike an in-memory counter.
    record=False checks without consuming (call again with limit=1 to record)."""
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
        if record:
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
        "ALTER TABLE projects ADD COLUMN views INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN starred INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN api_key TEXT",
        "ALTER TABLE users ADD COLUMN referral_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by TEXT",
        "ALTER TABLE users ADD COLUMN onboarded INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN team_id INTEGER",
        "ALTER TABLE team_members ADD COLUMN invited_email TEXT",
    ):
        try:
            con.execute(stmt)
        except Exception:
            pass
    con.executescript('''
    CREATE TABLE IF NOT EXISTS project_versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER, user_id INTEGER, markdown TEXT, note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER, user_id INTEGER, login TEXT, body TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS teams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER, name TEXT, created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS team_members(
        team_id INTEGER, user_id INTEGER, role TEXT DEFAULT 'viewer',
        PRIMARY KEY(team_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS api_keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, prefix TEXT, key_hash TEXT UNIQUE,
        scopes TEXT DEFAULT '*', created_at TEXT DEFAULT (datetime('now')),
        last_used_at TEXT, revoked INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_keys_hash ON api_keys(key_hash);
    CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, action TEXT, target TEXT, ip TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
    ''')
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
    """Resolve the caller. Accepts either the session cookie or an API key
    sent as 'Authorization: Bearer prd_...'. API keys are stored as SHA-256
    hashes; only the prefix is kept for display."""
    authz = request.headers.get('authorization', '')
    if authz.lower().startswith('bearer '):
        token = authz[7:].strip()
        if token.startswith('prd_'):
            con = _db()
            row = con.execute('''SELECT k.id AS key_id, u.* FROM api_keys k
                JOIN users u ON u.id=k.user_id
                WHERE k.key_hash=? AND k.revoked=0''', (_key_hash(token),)).fetchone()
            if row:
                con.execute("UPDATE api_keys SET last_used_at=datetime('now') WHERE id=?", (row['key_id'],))
                con.commit()
            con.close()
            if row:
                d = dict(row)
                d.pop('key_id', None)
                d['_auth'] = 'api_key'
                return d
            return None
    token = request.cookies.get('prd_session')
    uid = unsign(token) if token else None
    if not uid:
        return None
    con = _db()
    row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    con.close()
    return dict(row) if row else None


def _key_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _client_ip(request: Request):
    try:
        return (request.client.host if request.client else '') or ''
    except Exception:
        return ''


def audit(request: Request, user, action: str, target: str = ''):
    """Append an entry to the immutable audit trail. Never raises."""
    try:
        con = _db()
        con.execute('INSERT INTO audit_log(user_id,action,target,ip) VALUES(?,?,?,?)',
                    (user['id'] if user else None, action, (target or '')[:200], _client_ip(request)))
        con.commit(); con.close()
    except Exception:
        pass


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
    audit(request, {'id': row['id']}, 'login', 'github')
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
        audit(request, None, 'login_failed', email)
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
    # referral attribution: only accept codes that belong to an existing user
    ref = (body.get('referred_by') or '').strip()[:40]
    if ref and not con.execute('SELECT id FROM users WHERE referral_code=?', (ref,)).fetchone():
        ref = ''
    base = login
    n = 1
    while con.execute('SELECT id FROM users WHERE login=?', (login,)).fetchone():
        n += 1
        login = base + str(n)
    cur = con.execute('INSERT INTO users(github_id, login, name, email, plan, password, referred_by) VALUES(?,?,?,?,?,?,?) RETURNING id',
                      ('email:' + email, login, name or login, email, 'free', hash_password(pw), ref or None))
    con.commit()
    uid = cur.lastrowid
    con.close()
    audit(request, {'id': uid}, 'signup', email + (' ref=' + ref if ref else ''))
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
    audit(request, {'id': uid}, 'password_set_by_admin', str(uid))
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


PAKASIR_SLUG = os.environ.get('PAKASIR_SLUG', '')
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
    plan = (body.get('plan') or 'pro').strip()
    if plan != 'pro':
        raise HTTPException(400, 'unsupported plan')
    if not PAKASIR_SLUG:
        raise HTTPException(503, 'payment gateway not configured (PAKASIR_SLUG missing)')
    method = (body.get('method') or 'qris').strip()
    amount = PRICE_PRO  # server-decided; never trust a client-sent amount
    order = 'PRD' + secrets.token_hex(6).upper()
    con = _db()
    _ensure_orders(con)
    con.execute('INSERT INTO orders(id,user_id,plan,status,amount,method) VALUES(?,?,?,?,?,?)',
                (order, u['id'], plan, 'pending', amount, method))
    con.commit(); con.close()

    if not PAKASIR_API_KEY:
        return {'order': order, 'plan': plan, 'status': 'pending', 'configured': False,
                'amount': amount, 'method': method,
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
    # the secret is mandatory: without it anyone could mark orders paid
    if not PAKASIR_WEBHOOK_SECRET or not hmac.compare_digest(secret, PAKASIR_WEBHOOK_SECRET):
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
    audit(request, {'id': row['user_id']}, 'payment_' + (status or 'unknown'), order)
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


# ---- teams / collaboration ----
def _team_role(con, team_id, uid):
    r = con.execute('SELECT role FROM team_members WHERE team_id=? AND user_id=?', (team_id, uid)).fetchone()
    return r['role'] if r else None


@router.get('/api/teams')
def api_teams(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    owned = con.execute('SELECT id,name,created_at FROM teams WHERE owner_id=? ORDER BY id DESC', (u['id'],)).fetchall()
    joined = con.execute('''SELECT t.id,t.name,t.created_at,m.role FROM teams t
        JOIN team_members m ON m.team_id=t.id WHERE m.user_id=? ORDER BY t.id DESC''', (u['id'],)).fetchall()
    con.close()
    return {'owned': [dict(r) for r in owned], 'joined': [dict(r) for r in joined]}


@router.post('/api/teams')
async def api_team_create(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    name = (body.get('name') or '').strip()[:60]
    if not name:
        raise HTTPException(400, 'name required')
    con = _db()
    cur = con.execute('INSERT INTO teams(owner_id,name) VALUES(?,?) RETURNING id', (u['id'], name))
    tid = cur.lastrowid
    con.execute('INSERT OR IGNORE INTO team_members(team_id,user_id,role) VALUES(?,?,?)', (tid, u['id'], 'owner'))
    con.commit(); con.close()
    return {'id': tid, 'name': name}


@router.post('/api/teams/{tid}/invite')
async def api_team_invite(tid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    email = (body.get('email') or '').strip().lower()
    role = (body.get('role') or 'editor').strip()
    if not email:
        raise HTTPException(400, 'email required')
    con = _db()
    team = con.execute('SELECT * FROM teams WHERE id=?', (tid,)).fetchone()
    if not team or team['owner_id'] != u['id']:
        con.close(); raise HTTPException(403, 'not your team')
    target = con.execute('SELECT id FROM users WHERE lower(email)=?', (email,)).fetchone()
    if target:
        con.execute('INSERT OR IGNORE INTO team_members(team_id,user_id,role) VALUES(?,?,?)', (tid, target['id'], role))
    else:
        con.execute('INSERT INTO team_members(team_id,user_id,role,invited_email) VALUES(?,?,?,?)', (tid, None, role, email))
    con.commit(); con.close()
    return {'ok': True, 'email': email, 'matched': bool(target)}


@router.get('/api/teams/{tid}/members')
def api_team_members(tid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    rows = con.execute('''SELECT m.user_id, m.role, m.invited_email, u.login, u.name, u.email
        FROM team_members m LEFT JOIN users u ON u.id=m.user_id WHERE m.team_id=?''', (tid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post('/api/projects/{pid}/team')
async def api_project_team(pid: int, request: Request):
    """Assign a project to a team you own."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    tid = int(body.get('team_id') or 0)
    con = _db()
    own = con.execute('SELECT id FROM projects WHERE id=? AND user_id=?', (pid, u['id'])).fetchone()
    if not own:
        con.close(); raise HTTPException(404, 'not found')
    if tid:
        team = con.execute('SELECT owner_id FROM teams WHERE id=?', (tid,)).fetchone()
        if not team or team['owner_id'] != u['id']:
            con.close(); raise HTTPException(403, 'not your team')
    con.execute('UPDATE projects SET team_id=? WHERE id=?', (tid or None, pid))
    con.commit(); con.close()
    return {'ok': True, 'team_id': tid or None}


# ---- version history ----
@router.post('/api/projects/{pid}/versions')
async def api_version_save(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    md = body.get('markdown') or ''
    if not md:
        raise HTTPException(400, 'markdown required')
    con = _db()
    own = con.execute('SELECT id FROM projects WHERE id=? AND user_id=?', (pid, u['id'])).fetchone()
    if not own:
        con.close(); raise HTTPException(404, 'not found')
    con.execute('INSERT INTO project_versions(project_id,user_id,markdown,note) VALUES(?,?,?,?)',
                (pid, u['id'], md, (body.get('note') or '').strip()[:120]))
    con.commit(); con.close()
    return {'ok': True}


@router.get('/api/projects/{pid}/versions')
def api_versions(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    own = con.execute('SELECT id FROM projects WHERE id=? AND user_id=?', (pid, u['id'])).fetchone()
    if not own:
        con.close(); raise HTTPException(404, 'not found')
    rows = con.execute('SELECT id,note,created_at,length(markdown) chars FROM project_versions WHERE project_id=? ORDER BY id DESC LIMIT 50', (pid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.get('/api/versions/{vid}')
def api_version_get(vid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    row = con.execute('SELECT * FROM project_versions WHERE id=? AND user_id=?', (vid, u['id'])).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, 'not found')
    return dict(row)


def _project_visible(con, pid, u):
    """A project is visible to its owner, or when it is publicly shared."""
    row = con.execute('SELECT id, user_id, shared FROM projects WHERE id=?', (pid,)).fetchone()
    if not row:
        return None
    if row['shared']:
        return row
    if u and row['user_id'] == u['id']:
        return row
    return None


@router.get('/api/projects/{pid}/comments')
def api_comments(pid: int, request: Request):
    u = current_user(request)
    con = _db()
    if not _project_visible(con, pid, u):
        con.close()
        raise HTTPException(404, 'not found')
    rows = con.execute('SELECT id,login,body,created_at FROM comments WHERE project_id=? ORDER BY id ASC LIMIT 200', (pid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post('/api/projects/{pid}/comments')
async def api_comment_add(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    body = await request.json()
    text = (body.get('body') or '').strip()[:2000]
    if not text:
        raise HTTPException(400, 'empty comment')
    con = _db()
    if not _project_visible(con, pid, u):
        con.close()
        raise HTTPException(404, 'not found')
    con.execute('INSERT INTO comments(project_id,user_id,login,body) VALUES(?,?,?,?)',
                (pid, u['id'], u.get('login') or '', text))
    con.commit(); con.close()
    audit(request, u, 'comment_added', str(pid))
    return {'ok': True}


# ---- api keys (v2: multiple, hashed, revocable) ----
MAX_ACTIVE_KEYS = 20


class KeyReq(BaseModel):
    name: str = 'default'


@router.get('/api/keys')
def api_keys_list(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    rows = con.execute('''SELECT id, name, prefix, scopes, created_at, last_used_at, revoked
        FROM api_keys WHERE user_id=? ORDER BY id DESC''', (u['id'],)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post('/api/keys')
def api_keys_create(req: KeyReq, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    n = con.execute('SELECT COUNT(*) c FROM api_keys WHERE user_id=? AND revoked=0', (u['id'],)).fetchone()['c']
    if n >= MAX_ACTIVE_KEYS:
        con.close()
        raise HTTPException(400, 'too many active keys (max %d). Revoke one first.' % MAX_ACTIVE_KEYS)
    token = 'prd_' + secrets.token_hex(24)
    con.execute('INSERT INTO api_keys(user_id,name,prefix,key_hash) VALUES(?,?,?,?)',
                (u['id'], (req.name or 'default').strip()[:60], token[:12], _key_hash(token)))
    con.commit(); con.close()
    audit(request, u, 'apikey_created', (req.name or 'default').strip()[:60])
    # the full token is returned exactly once; only its hash is stored
    return {'api_key': token, 'prefix': token[:12], 'name': (req.name or 'default').strip()[:60]}


@router.post('/api/keys/{kid}/revoke')
def api_keys_revoke(kid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    row = con.execute('SELECT id FROM api_keys WHERE id=? AND user_id=?', (kid, u['id'])).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, 'key not found')
    con.execute('UPDATE api_keys SET revoked=1 WHERE id=?', (kid,))
    con.commit(); con.close()
    audit(request, u, 'apikey_revoked', str(kid))
    return {'ok': True, 'revoked': kid}


# ---- GDPR data export ----
@router.get('/api/me/export')
def api_me_export(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    projects = [dict(r) for r in con.execute(
        'SELECT id,name,template,payload,markdown,lang,created_at FROM projects WHERE user_id=?', (u['id'],)).fetchall()]
    usage = [dict(r) for r in con.execute(
        'SELECT kind,name,created_at FROM usage WHERE user_id=? ORDER BY id DESC LIMIT 1000', (u['id'],)).fetchall()]
    keys = [dict(r) for r in con.execute(
        'SELECT name,prefix,created_at,last_used_at FROM api_keys WHERE user_id=?', (u['id'],)).fetchall()]
    con.close()
    profile = {k: u.get(k) for k in ('id', 'login', 'name', 'email', 'plan', 'created_at')}
    return {'profile': profile, 'projects': projects, 'usage': usage, 'api_keys': keys,
            'exported_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


# ---- team project access (RBAC-lite) ----
@router.get('/api/teams/{tid}/projects')
def api_team_projects(tid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    role = _team_role(con, tid, u['id'])
    if not role:
        con.close()
        raise HTTPException(403, 'not a team member')
    rows = con.execute('''SELECT p.id, p.name, p.template, p.lang, p.created_at, u.login AS owner
        FROM projects p LEFT JOIN users u ON u.id=p.user_id
        WHERE p.team_id=? ORDER BY p.id DESC LIMIT 200''', (tid,)).fetchall()
    con.close()
    return {'role': role, 'projects': [dict(r) for r in rows]}


@router.get('/api/admin/audit')
def api_admin_audit(request: Request, limit: int = 300):
    _require_admin(request)
    limit = max(1, min(1000, limit))
    con = _db()
    rows = con.execute('''SELECT a.id, a.action, a.target, a.ip, a.created_at, u.login
        FROM audit_log a LEFT JOIN users u ON u.id=a.user_id
        ORDER BY a.id DESC LIMIT ?''', (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---- referral ----
def _ensure_referral(u):
    if u.get('referral_code'):
        return u['referral_code']
    code = (u.get('login') or 'user')[:12].lower() + secrets.token_hex(2)
    con = _db()
    con.execute('UPDATE users SET referral_code=? WHERE id=?', (code, u['id']))
    con.commit(); con.close()
    return code


@router.get('/api/referral')
def api_referral(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    code = _ensure_referral(u)
    con = _db()
    n = con.execute('SELECT COUNT(*) c FROM users WHERE referred_by=?', (code,)).fetchone()['c']
    con.close()
    return {'code': code, 'url': '/login?ref=' + code, 'invited': n}


# ---- public gallery ----
@router.get('/api/gallery')
def api_gallery(request: Request):
    con = _db()
    rows = con.execute('''SELECT p.share_id, p.name, p.template, p.lang, p.views, p.created_at, u.login
        FROM projects p LEFT JOIN users u ON u.id=p.user_id
        WHERE p.shared=1 ORDER BY p.views DESC, p.id DESC LIMIT 60''').fetchall()
    con.close()
    return [dict(r) for r in rows]


ADMIN_SECRET = os.environ.get('ADMIN_SECRET', '')
# no default: a hardcoded secret console path in a public repo defeats the point
ADMIN_PATH = os.environ.get('ADMIN_PATH', '')


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
    audit(request, {'id': uid}, 'plan_change', uid and str(uid) + ':' + plan)
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
    con.execute('DELETE FROM team_members WHERE user_id=?', (uid,))
    con.execute('DELETE FROM team_members WHERE team_id IN (SELECT id FROM teams WHERE owner_id=?)', (uid,))
    con.execute('DELETE FROM teams WHERE owner_id=?', (uid,))
    con.execute('DELETE FROM comments WHERE user_id=?', (uid,))
    con.execute('DELETE FROM project_versions WHERE user_id=?', (uid,))
    con.execute('DELETE FROM api_keys WHERE user_id=?', (uid,))
    con.execute('DELETE FROM orders WHERE user_id=?', (uid,))
    con.execute('DELETE FROM projects WHERE user_id=?', (uid,))
    con.execute('DELETE FROM usage WHERE user_id=?', (uid,))
    con.execute('DELETE FROM users WHERE id=?', (uid,))
    con.commit(); con.close()
    audit(request, {'id': None}, 'user_deleted', str(uid))
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
    cur = con.execute('INSERT INTO projects(user_id,name,template,payload,markdown,lang) VALUES(?,?,?,?,?,?) RETURNING id',
                      (u['id'], name, body.get('template', ''), json.dumps(body.get('payload', {})), markdown, body.get('lang', 'en')))
    con.commit()
    pid = cur.lastrowid
    con.close()
    audit(request, u, 'project_saved', str(pid))
    return {'id': pid}


@router.delete('/api/projects/{pid}')
def api_delete(pid: int, request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, 'login required')
    con = _db()
    con.execute('DELETE FROM projects WHERE id=? AND user_id=?', (pid, u['id']))
    con.commit(); con.close()
    audit(request, u, 'project_deleted', str(pid))
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
        audit(request, u, 'share_disabled', str(pid))
        return {'shared': False}
    sid = row['share_id'] or secrets.token_urlsafe(8)
    con.execute('UPDATE projects SET shared=1, share_id=? WHERE id=?', (sid, pid))
    con.commit(); con.close()
    audit(request, u, 'share_enabled', str(pid))
    lang = row['lang'] or 'en'
    return {'shared': True, 'share_id': sid, 'lang': lang, 'url': '/p/' + sid + '/' + lang}


@router.get('/api/shared/{sid}')
def api_shared(sid: str, request: Request):
    """Public read-only view of a shared project. No auth required."""
    con = _db()
    row = con.execute('SELECT id, name, template, markdown, lang, created_at, views FROM projects WHERE share_id=? AND shared=1', (sid,)).fetchone()
    if row:
        con.execute('UPDATE projects SET views=views+1 WHERE id=?', (row['id'],))
        con.commit()
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

    # translate the actual shared document (never regenerate it: content must
    # stay identical across languages)
    import server as _server
    lang_name = 'Bahasa Indonesia' if want == 'id' else 'English'
    md = _server.ai_chat(
        'Translate the following PRD document to ' + lang_name + '. Keep the exact same '
        'Markdown structure: same headings, tables, lists and order. Translate faithfully — '
        'do not add, remove or change any content. Return ONLY the translated document.',
        row['markdown'][:12000], max_tokens=2000, temperature=0.2, model_idx=1)
    con = _db()
    con.execute('INSERT OR REPLACE INTO shared_cache(share_id,lang,markdown) VALUES(?,?,?)', (sid, want, md))
    con.commit(); con.close()
    return {'markdown': md, 'lang': want, 'cached': False}
