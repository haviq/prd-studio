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

app = FastAPI(title='PRD Studio', docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

import auth
auth.init_db()
app.include_router(auth.router)

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
    if limit <= 0:
        return True
    now = time.time()
    with _lock:
        arr = [t for t in _hits.get(key, []) if now - t < WINDOW]
        if len(arr) >= limit:
            return False
        arr.append(now)
        _hits[key] = arr
        return True


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


def _base(r: GenReq):
    return ('App Name: ' + r.name + '\n'
            'Description: ' + r.description + '\n'
            'Main Features: ' + (r.features or 'not specified') + '\n'
            'Target Users: ' + (r.users or 'not specified') + '\n'
            'Tech Stack: ' + (r.tech or 'not specified') + '\n'
            'Product Type: ' + r.template)


@app.post('/api/generate')
def api_generate(req: GenReq, request: Request):
    ok, msg = _gate(request, 'generate')
    if not ok:
        raise HTTPException(429, msg)
    if not req.name.strip() or not req.description.strip():
        raise HTTPException(400, 'name and description are required')
    sys = ('You are a senior product manager and software architect writing a THOROUGH, '
           'production-grade PRD. Be specific and concrete: name real components, tables, '
           'endpoints, fields, libraries and steps. Use Markdown with sub-headings and bullet '
           'lists. Answer ONLY the requested sections, in English.')
    base = _base(req)
    ucfg = auth.user_ai_config(auth.current_user(request))
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
    auth.log_usage(auth.current_user(request), 'generate', req.name)
    return {'markdown': '\n\n'.join(buf)}


class ReviseReq(BaseModel):
    markdown: str
    instruction: str
    name: str = ''


# free accounts get 1 revision per PRD; pro is unlimited
REVISE_FREE = int(os.environ.get('REVISE_FREE', '1'))
_revise_hits = {}


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
    return {'ok': True, 'ai_configured': bool(AI_API_KEY), 'models': AI_MODELS}


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


# Serve any remaining static asset (images, video, etc.) from the static dir.
from fastapi.staticfiles import StaticFiles
app.mount('/', StaticFiles(directory=str(STATIC)), name='static')
