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


def ai_chat(system, user, max_tokens=700, temperature=0.4, model_idx=0):
    if not AI_API_KEY:
        raise RuntimeError('AI not configured')
    model = AI_MODELS[model_idx % len(AI_MODELS)]
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], 'temperature': temperature, 'max_tokens': max_tokens}
    r = httpx.post(AI_BASE_URL + '/chat/completions', json=body,
                   headers={'Authorization': 'Bearer ' + AI_API_KEY,
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
    try:
        raw = ai_chat(system, user, max_tokens=600)
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
    sys = ('You are a senior product manager writing a detailed, professional PRD. '
           'Answer ONLY the requested section, in English, in Markdown.')
    base = _base(req)
    buf = []
    try:
        buf.append(ai_chat(sys, 'PRD for:\n' + base + '\n\nWrite CONCISE bullet points (max 400 words) for:\n## 1. Overview & Goals\n## 2. Architecture\n## 3. API', 700, model_idx=0))
        buf.append(ai_chat(sys, 'PRD for:\n' + base + '\n\nWrite CONCISE bullet points (max 400 words) for:\n## 4. Database / ERD\n## 5. AI Prompt Design\n## 6. Security', 700, model_idx=1))
        buf.append(ai_chat(sys, 'PRD for:\n' + base + '\n\nWrite CONCISE bullet points (max 400 words) for:\n## 7. Testing Plan\n## 8. Deployment\n## 9. Roadmap', 700, model_idx=2))
    except Exception as e:
        raise HTTPException(502, 'ai failed: ' + str(e))
    return {'markdown': '\n\n'.join(buf)}


@app.post('/api/diagram')
def api_diagram(req: dict, request: Request):
    ok, msg = _gate(request, 'aux')
    if not ok:
        raise HTTPException(429, msg)
    kind = req.get('kind', 'arch')
    data = req
    base = ('App Name: ' + data.get('name', '') + '\nDescription: ' + data.get('description', '') + '\nFeatures: ' + data.get('features', ''))
    try:
        if kind == 'arch':
            raw = ai_chat('You are a software architect. Return ONLY valid Mermaid code in one ```mermaid``` block. No other text.',
                          'Create a Mermaid flowchart TD for the system architecture: ' + base, 500)
            code = _extract_mermaid(raw)
            if not code:
                raise RuntimeError('no mermaid')
            return {'kind': 'arch', 'lang': 'mermaid', 'code': code}
        else:
            raw = ai_chat('You are a database architect. Return ONLY valid Mermaid erDiagram code in one ```mermaid``` block. No other text.',
                          'Create a CONCISE Mermaid erDiagram (max 6 entities, with a few fields each) for: ' + base, 700)
            code = _extract_mermaid(raw)
            if not code:
                raise RuntimeError('no mermaid erd')
            return {'kind': 'erd', 'lang': 'mermaid', 'code': code}
    except Exception as e:
        raise HTTPException(502, 'diagram failed: ' + str(e))


def _extract_mermaid(raw):
    m = re.search(r'```mermaid\s*([\s\S]+?)```', raw)
    if m:
        return m.group(1).strip()
    if any(k in raw for k in ('flowchart', 'graph ', 'erDiagram', 'sequenceDiagram')):
        return raw.strip()
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


STATIC = BASE_DIR / 'static'


def page(name):
    return (STATIC / name).read_text(encoding='utf-8')


@app.get('/', response_class=HTMLResponse)
def index():
    return page('index.html')


@app.get('/features', response_class=HTMLResponse)
def features():
    return page('features.html')


@app.get('/docs', response_class=HTMLResponse)
def docs():
    return page('docs.html')


@app.get('/studio', response_class=HTMLResponse)
def studio():
    return page('studio.html')


@app.get('/account', response_class=HTMLResponse)
def account():
    return page('account.html')


@app.get('/account.js')
def account_js():
    from fastapi.responses import Response
    return Response(page('account.js'), media_type='application/javascript')


@app.get('/checkout', response_class=HTMLResponse)
def checkout():
    return page('checkout.html')


@app.get('/checkout.js')
def checkout_js():
    from fastapi.responses import Response
    return Response(page('checkout.js'), media_type='application/javascript')


@app.get('/terms', response_class=HTMLResponse)
def terms():
    return page('terms.html')


@app.get('/styles.css')
def styles():
    from fastapi.responses import Response
    return Response(page('styles.css'), media_type='text/css')


@app.get('/cookies.js')
def cookies_js():
    from fastapi.responses import Response
    return Response(page('cookies.js'), media_type='application/javascript')


@app.get('/reveal.js')
def reveal_js():
    from fastapi.responses import Response
    return Response(page('reveal.js'), media_type='application/javascript')


@app.get('/studio.js')
def studio_js():
    from fastapi.responses import Response
    return Response(page('studio.js'), media_type='application/javascript')
