<div align="center">

<img src="static/logo.svg" alt="PRD Studio" width="72" height="72" />

# PRD Studio

**Turn a one-line idea into a complete, thirteen-section PRD — with architecture and ERD diagrams — in under a minute.**

[![Live](https://img.shields.io/badge/live-prd.haaviq.dev-d97757?style=flat-square)](https://prd.haaviq.dev)
[![CI](https://img.shields.io/github/actions/workflow/status/haviq/prd-studio/ci.yml?style=flat-square&label=CI)](https://github.com/haviq/prd-studio/actions)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/license-Proprietary-b0aea5?style=flat-square)](#license)

[Live Demo](https://prd.haaviq.dev) · [Features](https://prd.haaviq.dev/features) · [Docs](https://prd.haaviq.dev/docs) · [Examples](https://prd.haaviq.dev/examples)

</div>

---

## Overview

Writing a product requirements document is the slow part of building.
PRD Studio drafts the whole thing — overview, scope, user stories, architecture,
API design, data model, security, testing, deployment and roadmap — plus the
diagrams, so you can start shipping.

Describe your product in one sentence. Get a review-ready spec back.

```
"A habit tracker with streaks and reminders"
        ↓
   complete PRD + architecture diagram + ERD
```

## Features

| | Feature | Description |
|---|---|---|
| 📄 | **13 PRD sections** | Overview, scope, features, user stories, architecture, API, data model, security, testing, deployment, roadmap and risks |
| 📐 | **Auto diagrams** | A Mermaid architecture diagram and an entity-relationship diagram, from the same brief |
| ✍️ | **Natural-language revision** | Ask for changes in plain language and the document is rewritten |
| 💾 | **Saved projects** | Save, list and revisit every spec from your account |
| 🔌 | **Bring your own model** | Any OpenAI-compatible endpoint, or Anthropic natively |
| 📤 | **Clean export** | Portable Markdown you can drop into Notion, Linear or GitHub |
| 🔐 | **GitHub sign-in** | OAuth login with session cookies |
| 🎚️ | **Tiered plans** | Guest, Free and Pro limits with a checkout flow |
| 🔑 | **API keys** | Multiple hashed & revocable keys, `Authorization: Bearer` on every `/api` route |
| 🧾 | **Audit log** | Immutable trail of logins, key changes, deletes, shares, plan & payment events |
| 👥 | **Teams** | Create teams, invite members with roles, share projects to a team |
| 📦 | **Data export** | Users can download all their own data (GDPR-style, one request) |
| 🛡️ | **Security headers** | nosniff, frame-ancestors 'none', referrer & permissions policy on every response |

## Tech stack

- **Backend** — Python 3.12, FastAPI
- **Frontend** — static HTML / CSS / JS, no build step
- **Database** — SQLite (accounts, projects, usage)
- **Auth** — GitHub OAuth
- **Diagrams** — Mermaid, rendered client-side
- **Deploy** — Docker + docker compose

## API

Base URL: `https://prd.haaviq.dev`

| Method | Endpoint | Description | Auth |
|:------:|----------|-------------|:----:|
| `GET`  | `/api/health` | Status, version and active models | — |
| `POST` | `/api/suggest` | Suggest fields from an app name | — |
| `POST` | `/api/generate` | Generate the full PRD | — |
| `POST` | `/api/revise` | Revise an existing PRD | — |
| `POST` | `/api/diagram` | Architecture and ERD | — |
| `GET`  | `/api/me` | Current session | — |
| `GET`  | `/api/me/export` | Download all your data (JSON) | ✅ |
| `GET`  | `/api/projects` | List saved projects | ✅ |
| `POST` | `/api/projects` | Save a project | ✅ |
| `GET`  | `/api/keys` | List your API keys | ✅ |
| `POST` | `/api/keys` | Create an API key (shown once) | ✅ |
| `POST` | `/api/keys/{id}/revoke` | Revoke an API key | ✅ |
| `GET`  | `/api/teams/{id}/projects` | Projects shared to a team you belong to | ✅ |
| `GET`  | `/api/admin/audit` | Audit trail (admin) | ⚙️ |

### API key authentication

Every `/api` route accepts either the session cookie or an API key:

```bash
# 1. Create a key in the account page (or via the API while signed in)
curl -X POST https://prd.haaviq.dev/api/keys -H 'Content-Type: application/json' \
  -b 'prd_session=...' -d '{"name": "ci"}'
# → {"api_key": "prd_x64...", "prefix": "prd_x64...", "name": "ci"}

# 2. Call the API with the bearer token
curl https://prd.haaviq.dev/api/projects \
  -H 'Authorization: Bearer prd_x64...'
```

Keys are stored as SHA-256 hashes — the full token is shown exactly once at
creation. Revoking a key takes effect immediately.

<details>
<summary><b>Example request</b></summary>

```bash
curl -s https://prd.haaviq.dev/api/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Habit Tracker",
    "desc": "Track habits with streaks and reminders",
    "type": "Mobile app"
  }'
```

</details>

## Getting started

### Prerequisites

- Python 3.12+
- Docker (for containerized deploy)

### Run locally

```bash
# 1. Clone
git clone https://github.com/haviq/prd-studio.git
cd prd-studio

# 2. Configure
cp .env.example .env
# edit .env and fill in your keys

# 3. Install
pip install -r requirements.txt

# 4. Run
uvicorn server:app --reload --port 8789
```

Open **http://127.0.0.1:8789**

### Run the tests

```bash
pip install -r requirements-dev.txt
pytest -q        # 11 tests: auth, projects, API keys, audit, RBAC, headers
ruff check .     # lint
```

CI (GitHub Actions) runs lint + tests on every push and builds the Docker
image on main — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

### Run with Docker

```bash
docker compose up -d --build
```

The app listens on port **8789**. Put it behind a reverse proxy with TLS for public use.

### Deploy free on Render (no persistent disk needed)

The default storage is SQLite, which needs a persistent disk. On hosts
without one (Render free tier, Koyeb, ...), point the app at
[Turso](https://turso.tech) — a hosted libSQL (SQLite-compatible) with a free
tier. The switch is automatic via two environment variables; no code changes.

```bash
# 1. Create the database (turso CLI, free signup)
turso db create prdstudio
turso db show prdstudio --url          # → TURSO_DATABASE_URL
turso db tokens create prdstudio       # → TURSO_AUTH_TOKEN

# 2. Deploy on Render
#    Dashboard → New + → Blueprint → pick this repo.
#    render.yaml pre-fills everything; set the sync:false vars:
#    TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, AI_API_KEY, AI_MODELS,
#    PUBLIC_URL (your render URL), GITHUB_CLIENT_ID/SECRET.
```

Turso mode is enabled only when both `TURSO_*` variables are set — locally the
app keeps using plain sqlite3 with zero configuration.

### Deploy free on Vercel (no sleep)

Vercel's Python runtime runs the whole app as a single ASGI function
(`api/index.py` + `vercel.json` are already in the repo). Hobby plan functions
run up to 300 s with Fluid compute — enough for full PRD generation.

1. Create the Turso database (see above) — required, since Vercel has no disk.
2. `vercel` CLI (or import the repo at vercel.com) → set the env vars:
   `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `AI_API_KEY`, `AI_MODELS`,
   `SESSION_SECRET`, `PUBLIC_URL` (your vercel URL), `GITHUB_CLIENT_ID/SECRET`.
3. Deploy. Everything (pages, API, static assets) is served by the function.

Caveats: the filesystem is ephemeral (`/tmp` only — logs and the fallback
SQLite path already point there), and the in-memory per-PRD revision counter
resets on cold starts; everything durable lives in Turso.

> Note: free Render instances sleep after 15 minutes of inactivity. Pair it
> with a free uptime pinger on `/api/health` (cron-job.org, UptimeRobot) to
> keep it warm.

## Configuration

All configuration is via environment variables — see [`.env.example`](.env.example).

| Variable | Description |
|----------|-------------|
| `AI_BASE_URL` | Base URL of the generation model |
| `AI_API_KEY` | API key for the model |
| `AI_MODELS` | Comma-separated model list |
| `PUBLIC_URL` | Public origin, used for OAuth callbacks |
| `SESSION_SECRET` | Long random string for session cookies |
| `GITHUB_CLIENT_ID` | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth app client secret |

## Project structure

```
prd-studio/
├── server.py          # FastAPI app + routes
├── auth.py            # GitHub OAuth, sessions, API keys, audit, DB
├── static/            # frontend (HTML / CSS / JS)
│   ├── index.html     # landing
│   ├── studio.html    # the studio
│   ├── docs.html      # API reference
│   └── ...
├── conftest.py        # pytest fixtures (test env)
├── test_app.py        # end-to-end API tests
├── ruff.toml          # lint config
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Security

- API keys: SHA-256 hashed at rest, prefix-only display, revocable, max 20 active per user
- Audit log: signups, logins (incl. failures), key lifecycle, deletes, shares, plan changes, payments
- Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`, `Referrer-Policy`, `Permissions-Policy`
- Passwords: PBKDF2-HMAC-SHA256, 120k iterations, per-user salt
- Sessions: HMAC-signed cookies, HttpOnly + Secure + SameSite=Lax
- Payments: webhook secret-verified before any plan upgrade

## Roadmap

- [x] PDF / DOCX export
- [x] Shareable public links
- [x] Team collaboration
- [x] API keys & audit log
- [ ] Stripe / Midtrans in addition to Pakasir
- [ ] SSO (Google / OIDC)
- [ ] Webhooks per user (PRD events)

## Contributing

This is a proprietary project. For questions or partnership, reach out at
**founder@haaviq.dev**.

## License

Proprietary. © 2026 PRD Studio.

<div align="center">
<br />
<sub>Built with care in Indonesia.</sub>
</div>
