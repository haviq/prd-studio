<div align="center">

<img src="static/logo.svg" alt="PRD Studio" width="72" height="72" />

# PRD Studio

**Turn a one-line idea into a complete, thirteen-section PRD — with architecture and ERD diagrams — in under a minute.**

[![Live](https://img.shields.io/badge/live-prd.haaviq.dev-d97757?style=flat-square)](https://prd.haaviq.dev)
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
| `GET`  | `/api/health` | Status and active models | — |
| `POST` | `/api/suggest` | Suggest fields from an app name | — |
| `POST` | `/api/generate` | Generate the full PRD | — |
| `POST` | `/api/revise` | Revise an existing PRD | — |
| `POST` | `/api/diagram` | Architecture and ERD | — |
| `GET`  | `/api/me` | Current session | — |
| `GET`  | `/api/projects` | List saved projects | ✅ |
| `POST` | `/api/projects` | Save a project | ✅ |

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
git clone https://github.com/haaviq/prd-studio.git
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

### Run with Docker

```bash
docker compose up -d --build
```

The app listens on port **8789**. Put it behind a reverse proxy with TLS for public use.

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
├── auth.py            # GitHub OAuth, sessions, DB
├── static/            # frontend (HTML / CSS / JS)
│   ├── index.html     # landing
│   ├── studio.html    # the studio
│   ├── docs.html      # API reference
│   └── ...
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Roadmap

- [ ] Real payment gateway (Stripe / Midtrans)
- [ ] PDF / DOCX export
- [ ] Shareable public links
- [ ] Team collaboration
- [ ] More sign-in providers

## Contributing

This is a proprietary project. For questions or partnership, reach out at
**founder@haaviq.dev**.

## License

Proprietary. © 2026 PRD Studio.

<div align="center">
<br />
<sub>Built with care in Indonesia.</sub>
</div>
