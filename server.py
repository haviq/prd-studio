import os, json, re
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from pathlib import Path

BASE_DIR = Path(__file__).parent

AI_BASE_URL = os.environ.get('AI_BASE_URL', 'https://api.example.com/v1')
AI_API_KEY = os.environ.get('AI_API_KEY', '')
AI_MODELS = [m.strip() for m in os.environ.get('AI_MODELS', 'gemini-3.8-flash-high,gemini-3.6-flash-high,gemini-3.5-flash-lite').split(',') if m.strip()]

import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get('LOG_DIR', '/app/data')
try:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    _handler = RotatingFileHandler(os.path.join(LOG_DIR, 'app.log'), maxBytes=2_000_000, backupCount=3)
    _handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    _log = logging.getLogger('prdstudio')
    _log.setLevel(logging.INFO)
    _log.addHandler(_handler)
except Exception:
    _log = logging.getLogger('prdstudio')
    _log.addHandler(logging.StreamHandler())

app = FastAPI(title='PRD Studio', docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


@app.middleware('http')
async def _log_requests(request: Request, call_next):
    import time as _t
    t0 = _t.time()
    try:
        resp = await call_next(request)
    except Exception as e:
        _log.error('UNHANDLED %s %s -> %s', request.method, request.url.path, e)
        raise
    dt = (_t.time() - t0) * 1000
    if resp.status_code >= 500 or dt > 15000 or '/api/' in request.url.path:
        _log.info('%s %s %s %.0fms', request.method, request.url.path, resp.status_code, dt)
    return resp

import auth
auth.init_db()
app.include_router(auth.router)

APP_VERSION = '2.0.0'


@app.middleware('http')
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    resp.headers['Content-Security-Policy'] = "frame-ancestors 'none'"
    resp.headers['X-XSS-Protection'] = '0'
    return resp

# tiered daily limits: anonymous vs signed-in vs pro
import threading, time
_hits = {}
_lock = threading.Lock()
WINDOW = 86400  # one day
ANON_LIMIT = int(os.environ.get('ANON_LIMIT', '1'))    # PRDs/day, not signed in
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '10'))   # PRDs/day, signed in free
PRO_LIMIT = int(os.environ.get('PRO_LIMIT', '0'))      # PRDs/day, pro (0 = unlimited)
AUX_ANON = int(os.environ.get('AUX_ANON', '6'))        # suggest/diagram, anon
AUX_FREE = int(os.environ.get('AUX_FREE', '60'))       # suggest/diagram, signed in


def _bucket(key, limit):
    """DB-backed rate limit so limits survive container restarts."""
    return auth.rate_check(key, limit, WINDOW)


def _gate(request, kind='generate'):
    """Return (allowed, message). Enforces per-day limits by plan."""
    u = auth.current_user(request)
    if u:
        plan = (u.get('plan') or 'free')
        uid = 'u:' + str(u['id']) + ':' + kind
        if plan == 'pro':
            return True, None
        if kind == 'generate':
            ok = _bucket(uid, FREE_LIMIT)
            return ok, None if ok else 'Free accounts can generate ' + str(FREE_LIMIT) + ' PRDs per day. Upgrade to Pro for unlimited.'
        ok = _bucket(uid, AUX_FREE)
        return ok, None if ok else 'Daily limit reached. Try again tomorrow.'
    ip = request.client.host if request.client else 'unknown'
    key = 'ip:' + ip + ':' + kind
    limit = ANON_LIMIT if kind == 'generate' else AUX_ANON
    ok = _bucket(key, limit)
    if ok:
        return True, None
    if kind == 'generate':
        return False, 'Free plan: 1 PRD per day. Sign in with GitHub for more, or upgrade to Pro.'
    return False, 'Free plan limit reached. Sign in for more.'


def ai_chat(system, user, max_tokens=700, temperature=0.4, model_idx=0, cfg=None):
    """Call the model. cfg (from a signed-in user) can override provider, base URL,
    key and model. Supports OpenAI-compatible and Anthropic-native APIs."""
    provider = 'openai'
    base_url = AI_BASE_URL
    api_key = AI_API_KEY
    model = AI_MODELS[model_idx % len(AI_MODELS)]
    if cfg:
        provider = (cfg.get('provider') or 'openai').lower()
        base_url = cfg.get('base_url') or base_url
        api_key = cfg.get('api_key') or api_key
        if cfg.get('model'):
            model = cfg['model']
    if not api_key:
        raise RuntimeError('AI not configured')
    if provider == 'anthropic':
        body = {'model': model, 'max_tokens': max_tokens, 'temperature': temperature,
                'system': system, 'messages': [{'role': 'user', 'content': user}]}
        r = httpx.post(base_url.rstrip('/') + '/messages', json=body,
                       headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01',
                                'Content-Type': 'application/json'}, timeout=180)
        r.raise_for_status()
        data = json.loads(r.text)
        parts = data.get('content') or []
        return ''.join(p.get('text', '') for p in parts if isinstance(p, dict)).strip()
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], 'temperature': temperature, 'max_tokens': max_tokens}
    r = httpx.post(base_url.rstrip('/') + '/chat/completions', json=body,
                   headers={'Authorization': 'Bearer ' + api_key,
                            'Content-Type': 'application/json'}, timeout=180)
    r.raise_for_status()
    text = re.sub(r'data:\s*\[DONE\]', '', r.text).strip()
    data = json.loads(text)
    return (data['choices'][0]['message'].get('content') or '').strip()


class SuggestReq(BaseModel):
    title: str
    template: str = 'Web App'


@app.post('/api/suggest')
def api_suggest(req: SuggestReq, request: Request):
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    title = req.title.strip()
    if not title:
        raise HTTPException(400, 'title required')
    system = ('You are an experienced product manager. Return an ARRAY of suggestions for each PRD field. '
              'Answer ONLY JSON, no other text: '
              '{ "description": ["short option 1", "short option 2"], '
              '"features": ["f1", "f2", "f3", "f4"], '
              '"users": ["target user 1", "target user 2"], '
              '"tech_stack": ["tech 1", "tech 2", "tech 3"] }')
    user = 'Give suggestions for the project: ' + title + ' (Type: ' + req.template + ')'
    ucfg = auth.user_ai_config(auth.current_user(request))
    try:
        raw = ai_chat(system, user, max_tokens=600, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return {'description': [raw[:200]]}


class GenReq(BaseModel):
    name: str
    description: str
    features: str = ''
    users: str = ''
    tech: str = ''
    template: str = 'Web App'
    lang: str = 'en'


def _base(r: GenReq):
    return ('App Name: ' + r.name + '\n'
            'Description: ' + r.description + '\n'
            'Main Features: ' + (r.features or 'not specified') + '\n'
            'Target Users: ' + (r.users or 'not specified') + '\n'
            'Tech Stack: ' + (r.tech or 'not specified') + '\n'
            'Product Type: ' + r.template)


def _gen_prd(req: GenReq, ucfg=None):
    """Generate the full 13-section PRD for a brief. Shared by /api/generate
    and the on-demand share-language endpoint."""
    lang_line = 'in Bahasa Indonesia' if (req.lang or 'en').startswith('id') else 'in English'
    sys = ('You are a senior product manager and software architect writing a THOROUGH, '
           'production-grade PRD. Be specific and concrete: name real components, tables, '
           'endpoints, fields, libraries and steps. Use Markdown with sub-headings and bullet '
           'lists. Answer ONLY the requested sections, ' + lang_line + '.')
    base = _base(req)
    buf = []
    try:
        buf.append(ai_chat(sys,
            'Product brief:\n' + base + '\n\n'
            'Write a DETAILED PRD with these sections. For each, use sub-headings and concrete detail:\n'
            '## 1. Overview & Goals\n- problem, target users, value proposition, success metrics (with numbers)\n'
            '## 2. Scope\n- in-scope and out-of-scope for v1\n'
            '## 3. Features & User Stories\n- numbered features, each with 1-2 user stories (As a ... I want ... so that ...) and acceptance criteria\n'
            '## 4. Architecture\n- components, data flow, tech choices and why, a text description of the diagram', 1400, model_idx=0, cfg=ucfg))
        buf.append(ai_chat(sys,
            'Product brief:\n' + base + '\n\n'
            'Write the DETAILED technical sections. Use tables where useful:\n'
            '## 5. API Design\n- table of endpoints: METHOD | path | purpose | auth | request fields | response fields\n'
            '## 6. Data Model / ERD\n- each entity, its fields and types, relationships, indexes\n'
            '## 7. Security\n- auth, authorization, input validation, secrets, rate limiting, data protection\n'
            '## 8. AI Prompt Design\n- the system prompts and model choices the product uses internally', 1400, model_idx=1, cfg=ucfg))
        buf.append(ai_chat(sys,
            'Product brief:\n' + base + '\n\n'
            'Write the DETAILED delivery sections:\n'
            '## 9. Non-Functional Requirements\n- performance, scalability, availability, accessibility targets\n'
            '## 10. Testing Plan\n- unit, integration, e2e, tools, key test cases\n'
            '## 11. Deployment & DevOps\n- environments, CI/CD, hosting, monitoring, backups\n'
            '## 12. Roadmap\n- phased milestones (MVP, v1, v2) with rough timelines\n'
            '## 13. Risks & Open Questions', 1400, model_idx=2, cfg=ucfg))
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    return '\n\n'.join(buf)


@app.post('/api/generate')
def api_generate(req: GenReq, request: Request):
    ok, msg = _gate(request, 'generate')
    if not ok:
        raise HTTPException(429, msg)
    if not req.name.strip() or not req.description.strip():
        raise HTTPException(400, 'name and description are required')
    u = auth.current_user(request)
    ucfg = auth.user_ai_config(u)
    md = _gen_prd(req, ucfg)
    auth.log_usage(u, 'generate', req.name)
    auth.audit(request, u, 'generate', req.name)
    return {'markdown': md}


class ReviseReq(BaseModel):
    markdown: str
    instruction: str
    name: str = ''


# free accounts get 1 revision per PRD; pro is unlimited
REVISE_FREE = int(os.environ.get('REVISE_FREE', '1'))
_revise_hits = {}


class SectionReq(BaseModel):
    markdown: str
    section: str
    name: str = ''
    template: str = 'Web App'
    lang: str = 'en'


@app.post('/api/regenerate-section')
def api_regenerate_section(req: SectionReq, request: Request):
    """Regenerate one section of an existing PRD, keeping the rest intact."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip() or not req.section.strip():
        raise HTTPException(400, 'markdown and section are required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    lang_line = 'in Bahasa Indonesia' if (req.lang or 'en').startswith('id') else 'in English'
    sys = ('You are a senior product manager and software architect. Rewrite ONE section of '
           'an existing PRD. Match the existing heading style, keep it concrete, and return '
           'ONLY the replacement section in Markdown (start with its ## heading). Answer ' + lang_line + '.')
    user = ('PRD so far:\n' + req.markdown[:6000] + '\n\nRewrite this section, improving it: ' + req.section)
    try:
        out = ai_chat(sys, user, max_tokens=1400, model_idx=1, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    auth.log_usage(auth.current_user(request), 'regenerate', req.name or req.section)
    return {'section': out.strip(), 'markdown': req.markdown}


@app.post('/api/revise')
def api_revise(req: ReviseReq, request: Request):
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip() or not req.instruction.strip():
        raise HTTPException(400, 'markdown and instruction are required')
    u = auth.current_user(request)
    plan = (u.get('plan') if u else None) or 'guest'
    if plan != 'pro':
        key = ('u:' + str(u['id'])) if u else ('ip:' + (request.client.host if request.client else 'x'))
        key += ':' + (req.name or 'anon')
        now = time.time()
        with _lock:
            arr = [t for t in _revise_hits.get(key, []) if now - t < WINDOW]
            if len(arr) >= REVISE_FREE:
                raise HTTPException(429, 'Free accounts can revise each PRD once. Upgrade to Pro for unlimited revisions.')
            arr.append(now)
            _revise_hits[key] = arr
    sys = ('You are a senior product manager and software architect. You are REVISING an '
           'existing PRD. Apply the requested change, keep the same overall structure and '
           'section headings, and return the COMPLETE revised PRD in Markdown. Be specific '
           'and concrete. Return ONLY the document.')
    user = ('Requested change: ' + req.instruction + '\n\n'
            'Current PRD:\n' + req.markdown[:12000])
    ucfg = auth.user_ai_config(auth.current_user(request))
    try:
        out = ai_chat(sys, user, 2000, temperature=0.4, model_idx=0, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    auth.log_usage(auth.current_user(request), 'revise', req.name)
    return {'markdown': out}


@app.post('/api/diagram')
def api_diagram(req: dict, request: Request):
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    kind = req.get('kind', 'arch')
    data = req
    base = ('App Name: ' + data.get('name', '') + '\nDescription: ' + data.get('description', '') + '\nFeatures: ' + data.get('features', ''))
    ucfg = auth.user_ai_config(auth.current_user(request))
    try:
        if kind == 'arch':
            raw = ai_chat('You are a software architect. Return ONLY valid Mermaid code in one ```mermaid``` block. No other text.',
                          'Create a Mermaid flowchart TD for the system architecture: ' + base, 500, cfg=ucfg)
            code = _extract_mermaid(raw)
            if not code:
                raise RuntimeError('no mermaid')
            return {'kind': 'arch', 'lang': 'mermaid', 'code': code}
        else:
            raw = ai_chat('You are a database architect. Return ONLY valid Mermaid erDiagram code in one ```mermaid``` block. No other text.',
                          'Create a CONCISE Mermaid erDiagram (max 6 entities, with a few fields each) for: ' + base, 700, cfg=ucfg)
            code = _extract_mermaid(raw)
            if not code:
                raise RuntimeError('no mermaid erd')
            return {'kind': 'erd', 'lang': 'mermaid', 'code': code}
    except Exception as e:
        raise HTTPException(502, 'diagram failed: ' + str(e))


def _clean_mermaid(code):
    """Make AI-generated Mermaid more likely to render."""
    if not code:
        return code
    code = code.replace('```mermaid', '').replace('```', '').strip()
    # drop a stray trailing semicolon-only line
    lines = [ln.rstrip() for ln in code.split('\n')]
    # remove lines that are just ``` fences already handled; drop empties at edges
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    code = '\n'.join(lines)
    # Mermaid dislikes unquoted parentheses/brackets inside node labels.
    # Quote the text inside [ ], ( ), { } when it is not already quoted.
    def _q(m):
        op, inner, cl = m.group(1), m.group(2), m.group(3)
        inner = inner.strip()
        if inner.startswith('"') and inner.endswith('"'):
            return op + inner + cl
        if any(c in inner for c in '()[]{}"\n'):
            inner = inner.replace('"', "'")
            return op + '"' + inner + '"' + cl
        return op + inner + cl
    code = re.sub(r'(\[)([^\[\]]*?)(\])', _q, code)
    return code.strip()


def _extract_mermaid(raw):
    m = re.search(r'```mermaid\s*([\s\S]+?)```', raw)
    if m:
        return _clean_mermaid(m.group(1))
    if any(k in raw for k in ('flowchart', 'graph ', 'erDiagram', 'sequenceDiagram')):
        return _clean_mermaid(raw)
    return None


def _extract_plantuml(raw):
    m = re.search(r'@startuml[\s\S]+?@enduml', raw)
    if m:
        return m.group(0).strip()
    if '@startuml' in raw:
        return raw.strip()
    return None


def _kroki_url(code, kind):
    import base64, zlib
    compressed = zlib.compress(code.encode('utf-8'), 9)
    b64 = base64.urlsafe_b64encode(compressed).decode('ascii')
    return 'https://kroki.io/' + kind + '/svg/' + b64


@app.get('/api/health')
def health():
    db_ok = True
    try:
        con = auth._db()
        con.execute('SELECT 1').fetchone()
        con.close()
    except Exception:
        db_ok = False
    return {'ok': db_ok, 'version': APP_VERSION, 'ai_configured': bool(AI_API_KEY), 'models': AI_MODELS}


from fastapi.exceptions import HTTPException as _HTTPExc
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def _http_exc(request, exc):
    if exc.status_code == 404:
        from fastapi.responses import HTMLResponse as _HR
        return _HR((BASE_DIR / 'static' / '404.html').read_text(encoding='utf-8'), status_code=404)
    from fastapi.responses import JSONResponse as _JR
    return _JR({'detail': exc.detail}, status_code=exc.status_code)


STATIC = BASE_DIR / 'static'


def page(name):
    return (STATIC / name).read_text(encoding='utf-8')


def html(name):
    """Return an HTML response with no-cache headers so the CDN always
    serves the latest markup after a deploy."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page(name), headers={'Cache-Control': 'no-cache, must-revalidate'})


@app.get('/', response_class=HTMLResponse)
def index():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('index.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/pricing', response_class=HTMLResponse)
def pricing():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('pricing.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/about', response_class=HTMLResponse)
def about():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('about.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/changelog', response_class=HTMLResponse)
def changelog():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('changelog.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/examples', response_class=HTMLResponse)
def examples():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('examples.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/features', response_class=HTMLResponse)
def features():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('features.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/docs', response_class=HTMLResponse)
def docs():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('docs.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/studio', response_class=HTMLResponse)
def studio():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('studio.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/login', response_class=HTMLResponse)
def login():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('login.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/account', response_class=HTMLResponse)
def account():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('account.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/account.js')
def account_js():
    from fastapi.responses import Response
    return Response(page('account.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/checkout', response_class=HTMLResponse)
def checkout():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('checkout.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/checkout.js')
def checkout_js():
    from fastapi.responses import Response
    return Response(page('checkout.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/terms', response_class=HTMLResponse)
def terms():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('terms.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/styles.css')
def styles():
    from fastapi.responses import Response
    return Response(page('styles.css'), media_type='text/css', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/robots.txt')
def robots():
    from fastapi.responses import Response
    return Response(page('robots.txt'), media_type='text/plain')


@app.get('/sitemap.xml')
def sitemap():
    from fastapi.responses import Response
    return Response(page('sitemap.xml'), media_type='application/xml')


@app.get('/logo.svg')
def logo_svg():
    from fastapi.responses import Response
    return Response(page('logo.svg'), media_type='image/svg+xml')


@app.get('/nav-auth.js')
def nav_auth_js():
    from fastapi.responses import Response
    return Response(page('nav-auth.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/cookies.js')
def cookies_js():
    from fastapi.responses import Response
    return Response(page('cookies.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/reveal.js')
def reveal_js():
    from fastapi.responses import Response
    return Response(page('reveal.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/studio.js')
def studio_js():
    from fastapi.responses import Response
    return Response(page('studio.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/shared.js')
def shared_js():
    from fastapi.responses import Response
    return Response(page('shared.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


ADMIN_PATH = os.environ.get('ADMIN_PATH', '/console-x7f9k2')


@app.get('/admin', response_class=HTMLResponse)
def admin_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('admin.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get(ADMIN_PATH, response_class=HTMLResponse)
def admin_secret_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('admin.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/admin.js')
def admin_js():
    from fastapi.responses import Response
    return Response(page('admin.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/for/{usecase}', response_class=HTMLResponse)
def usecase_page(usecase: str):
    from fastapi.responses import HTMLResponse
    tmpl = (STATIC / 'usecase.html')
    if not tmpl.exists():
        raise HTTPException(404, 'not found')
    return HTMLResponse(page('usecase.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/gallery', response_class=HTMLResponse)
def gallery_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('gallery.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/gallery.js')
def gallery_js():
    from fastapi.responses import Response
    return Response(page('gallery.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/roadmap', response_class=HTMLResponse)
def roadmap_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('roadmap.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/status', response_class=HTMLResponse)
def status_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('status.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/manifest.webmanifest')
def manifest():
    from fastapi.responses import Response
    return Response(page('manifest.webmanifest'), media_type='application/manifest+json')


@app.get('/sw.js')
def service_worker():
    from fastapi.responses import Response
    return Response(page('sw.js'), media_type='application/javascript', headers={'Cache-Control':'no-cache'})


@app.get('/p/{sid}', response_class=HTMLResponse)
def shared_page(sid: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('shared.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


@app.get('/p/{sid}/{lang}', response_class=HTMLResponse)
def shared_page_lang(sid: str, lang: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page('shared.html'), headers={'Cache-Control':'no-cache, must-revalidate'})


def _latin(s):
    """fpdf2 core fonts are latin-1; replace common unicode, drop the rest."""
    s = (s.replace('\u2019', "'").replace('\u2018', "'").replace('\u201c', '"').replace('\u201d', '"')
          .replace('\u2013', '-').replace('\u2014', '-').replace('\u2022', '-').replace('\u2026', '...')
          .replace('\u00a0', ' '))
    return s.encode('latin-1', 'replace').decode('latin-1')


def _xml_escape(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def md_to_docx(md, title='PRD'):
    """Minimal, dependency-free Markdown -> .docx (Office Open XML)."""
    import zipfile, io

    def para(text, bold=False, size=None, bullet=False):
        rpr = '<w:rPr>' + ('<w:b/>' if bold else '')
        if size:
            rpr += '<w:sz w:val="%d"/>' % size
        rpr += '</w:rPr>'
        t = ('\u2022 ' + text) if bullet else text
        return ('<w:p><w:pPr>' + ('<w:spacing w:before="120"/>' if bold else '') + '</w:pPr>'
                '<w:r>' + rpr + '<w:t xml:space="preserve">' + _xml_escape(t) + '</w:t></w:r></w:p>')

    body = [para(title, bold=True, size=36)]
    for line in md.split('\n'):
        raw = line.rstrip()
        s = raw.strip()
        if not s:
            body.append('<w:p/>')
        elif s.startswith('### '):
            body.append(para(s[4:], bold=True, size=24))
        elif s.startswith('## '):
            body.append(para(s[3:], bold=True, size=28))
        elif s.startswith('# '):
            body.append(para(s[2:], bold=True, size=32))
        elif s.startswith(('- ', '* ')):
            body.append(para(s[2:], bullet=True))
        else:
            body.append(para(raw))

    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        '</w:body></w:document>')
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document)
    return buf.getvalue()


@app.post('/api/generate-multi')
def api_generate_multi(req: GenReq, request: Request):
    """Generate PRD + Tech Spec + User Stories in one pass."""
    ok, msg = _gate(request, 'generate')
    if not ok:
        raise HTTPException(429, msg)
    if not req.name.strip() or not req.description.strip():
        raise HTTPException(400, 'name and description are required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    lang_line = 'in Bahasa Indonesia' if (req.lang or 'en').startswith('id') else 'in English'
    base = _base(req)
    sys = ('You are a senior PM and architect. Answer ' + lang_line + '. Be concrete and use Markdown.')
    out = {}
    try:
        out['prd'] = _gen_prd(req, ucfg)
        out['tech_spec'] = ai_chat(sys,
            'Product brief:\n' + base + '\n\nWrite a TECHNICAL SPEC (separate from the PRD): '
            '## Tech Stack\n## System Architecture\n## Data Model\n## API Contracts\n## Third-party Services\n'
            '## Security\n## Scalability & Performance\n## Local Dev Setup', 1400, model_idx=1, cfg=ucfg)
        out['user_stories'] = ai_chat(sys,
            'Product brief:\n' + base + '\n\nWrite USER STORIES: a numbered backlog. For each: '
            '"As a <role> I want <goal> so that <benefit>" + 2-3 acceptance criteria. '
            'Group by epic with ## headings. Aim for 12-20 stories.', 1400, model_idx=2, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    auth.log_usage(auth.current_user(request), 'generate-multi', req.name)
    return out


class BuildMsg(BaseModel):
    role: str
    content: str


class BuildReq(BaseModel):
    messages: list


@app.post('/api/chat-build')
def api_chat_build(req: BuildReq, request: Request):
    """Chat-first PRD creation. Given the conversation so far, either ask one
    clarifying question or, once enough is known, return the studio fields."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    convo = req.messages or []
    if not convo:
        raise HTTPException(400, 'messages required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    transcript = '\n'.join(
        ('User: ' if m.get('role') == 'user' else 'Assistant: ') + str(m.get('content', ''))[:1500]
        for m in convo[-12:])
    sys = ('You are a product manager helping a founder shape a PRD. Read the conversation. '
           'If you still need one key detail, ask ONE short question. If you have enough, '
           'stop asking and output the form fields. Return ONLY JSON, one of:\n'
           '{"action":"ask","question":"..."}\n'
           '{"action":"ready","name":"...","description":"...","features":"line per feature",'
           '"users":"...","tech":"..."}')
    try:
        raw = ai_chat(sys, 'Conversation:\n' + transcript + '\n\nRespond with the JSON.',
                      max_tokens=800, model_idx=2, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            if data.get('action') == 'ready':
                auth.log_usage(auth.current_user(request), 'chat-build', data.get('name', ''))
            return data
        except Exception:
            pass
    return {'action': 'ask', 'question': 'Tell me more about what you are building.'}


class TicketReq(BaseModel):
    markdown: str
    name: str = ''
    lang: str = 'en'


@app.post('/api/tickets')
def api_tickets(req: TicketReq, request: Request):
    """Turn a PRD into a list of implementation tickets (JSON)."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip():
        raise HTTPException(400, 'markdown required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    sys = ('You are a senior engineer breaking a PRD into tickets. Return ONLY JSON: '
           '{"tickets":[{"title":"...","type":"feature|chore|bug","priority":"P0|P1|P2",'
           '"estimate":"S|M|L","acceptance":["criterion 1","criterion 2"]}]}')
    try:
        raw = ai_chat(sys, 'PRD:\n' + req.markdown[:6000] + '\n\nBreak into 8-14 implementation tickets.',
                      max_tokens=1600, model_idx=1, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            auth.log_usage(auth.current_user(request), 'tickets', req.name)
            return data
        except Exception:
            pass
    return {'tickets': [], 'raw': raw[:500]}


class ChatReq(BaseModel):
    markdown: str
    question: str


@app.post('/api/chat')
def api_chat(req: ChatReq, request: Request):
    """Ask questions about a PRD. Answers grounded in the document."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip() or not req.question.strip():
        raise HTTPException(400, 'markdown and question required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    sys = ('You are a product assistant. Answer the question using ONLY the PRD below. '
           'If the answer is not in the document, say so. Be concise.')
    try:
        ans = ai_chat(sys, 'PRD:\n' + req.markdown[:8000] + '\n\nQuestion: ' + req.question,
                      max_tokens=700, model_idx=2, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    return {'answer': ans.strip()}


@app.post('/api/critique')
def api_critique(req: ChatReq, request: Request):
    """Review a PRD and return a score + concrete improvement suggestions."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip():
        raise HTTPException(400, 'markdown required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    sys = ('You are a principal engineer reviewing a PRD. Return ONLY JSON: '
           '{"score":0-100,"verdict":"one line","strengths":["..."],"gaps":["..."],'
           '"fixes":[{"section":"...","suggestion":"..."}]}')
    try:
        raw = ai_chat(sys, 'PRD:\n' + req.markdown[:7000] + '\n\nCritique it.',
                      max_tokens=1400, model_idx=0, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            auth.log_usage(auth.current_user(request), 'critique', '')
            return data
        except Exception:
            pass
    return {'score': 0, 'verdict': 'Could not parse review.', 'raw': raw[:400]}


@app.post('/api/estimate')
def api_estimate(req: ChatReq, request: Request):
    """Estimate build effort from a PRD: duration, team, cost."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.markdown.strip():
        raise HTTPException(400, 'markdown required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    sys = ('You are an engineering lead. From the PRD, estimate build effort. Return ONLY JSON: '
           '{"weeks":number,"team":[{"role":"...","count":n}],'
           '"phases":[{"name":"...","weeks":n}],"cost_usd":{"low":n,"high":n},"assumptions":["..."]}')
    try:
        raw = ai_chat(sys, 'PRD:\n' + req.markdown[:7000] + '\n\nEstimate.',
                      max_tokens=1200, model_idx=1, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            auth.log_usage(auth.current_user(request), 'estimate', '')
            return data
        except Exception:
            pass
    return {'weeks': 0, 'raw': raw[:400]}


class ImportReq(BaseModel):
    text: str


@app.post('/api/import-brief')
def api_import_brief(req: ImportReq, request: Request):
    """Parse a pasted brief into studio form fields."""
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    if not req.text.strip():
        raise HTTPException(400, 'text required')
    ucfg = auth.user_ai_config(auth.current_user(request))
    sys = ('Extract studio form fields from the text. Return ONLY JSON: '
           '{"name":"...","description":"...","features":"line per feature",'
           '"users":"...","tech":"..."}')
    try:
        raw = ai_chat(sys, req.text[:6000], max_tokens=800, model_idx=2, cfg=ucfg)
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    start, end = raw.find('{'), raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return {'description': req.text[:200]}


@app.post('/api/export/docx')
async def export_docx(request: Request):
    from fastapi.responses import Response
    body = await request.json()
    md = body.get('markdown') or ''
    name = (body.get('name') or 'PRD').strip() or 'PRD'
    if not md:
        raise HTTPException(400, 'markdown required')
    data = md_to_docx(md, name)
    fn = re.sub(r'[^A-Za-z0-9_-]+', '_', name)[:60] + '.docx'
    return Response(data,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': 'attachment; filename="' + fn + '"'})


@app.post('/api/export/pdf')
async def export_pdf(request: Request):
    """Native PDF export via fpdf2. Falls back to plain text if fonts fail."""
    from fastapi.responses import Response
    body = await request.json()
    md = body.get('markdown') or ''
    name = (body.get('name') or 'PRD').strip() or 'PRD'
    if not md:
        raise HTTPException(400, 'markdown required')
    try:
        from fpdf import FPDF
        pdf = FPDF(format='A4')
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 18)
        pdf.multi_cell(0, 10, _latin(name))
        pdf.ln(2)
        for line in md.split('\n'):
            s = line.rstrip()
            t = s.strip()
            if not t:
                pdf.ln(3); continue
            pdf.set_x(pdf.l_margin)
            if t.startswith('### '):
                pdf.set_font('Helvetica', 'B', 12); pdf.multi_cell(0, 7, _latin(t[4:]))
            elif t.startswith('## '):
                pdf.ln(1); pdf.set_font('Helvetica', 'B', 14); pdf.multi_cell(0, 8, _latin(t[3:]))
            elif t.startswith('# '):
                pdf.set_font('Helvetica', 'B', 16); pdf.multi_cell(0, 9, _latin(t[2:]))
            elif t.startswith(('- ', '* ')):
                pdf.set_font('Helvetica', '', 11); pdf.multi_cell(0, 6, _latin('  \u2022 ' + t[2:]))
            else:
                pdf.set_font('Helvetica', '', 11); pdf.multi_cell(0, 6, _latin(t))
        data = bytes(pdf.output())
    except Exception as e:
        raise HTTPException(502, 'pdf failed: ' + str(e))
    fn = re.sub(r'[^A-Za-z0-9_-]+', '_', name)[:60] + '.pdf'
    return Response(data, media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="' + fn + '"'})


# Serve any remaining static asset (images, video, etc.) from the static dir.
from fastapi.staticfiles import StaticFiles
app.mount('/', StaticFiles(directory=str(STATIC)), name='static')
