# PRD Studio

Turn a one-line product idea into a complete, thirteen-section Product
Requirements Document - with architecture and entity-relationship diagrams -
in under a minute.

Live: https://prd.haaviq.dev

## What it does

Describe your product in a sentence. PRD Studio writes the overview, scope,
features and user stories, architecture, API design, data model, security,
testing, deployment and roadmap, plus Mermaid diagrams for the architecture
and the ERD.

- 13 structured PRD sections
- Architecture diagram and ERD, generated from the same brief
- Natural-language revision on any document
- Save, list and revisit projects per account
- Bring your own model: any OpenAI-compatible endpoint or Anthropic natively
- Export to clean Markdown

## Stack

- Python (FastAPI) backend
- Static HTML/CSS/JS frontend, no build step
- SQLite for accounts, projects and usage
- GitHub OAuth for sign-in
- Docker + docker compose for deployment
- Mermaid rendered client-side

## API

Base URL: `https://prd.haaviq.dev`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Status and active models |
| POST | `/api/suggest` | Suggest fields from an app name |
| POST | `/api/generate` | Generate the full PRD |
| POST | `/api/revise` | Revise an existing PRD |
| POST | `/api/diagram` | Architecture and ERD |
| GET | `/api/me` | Current session |
| GET | `/api/projects` | List saved projects (auth) |
| POST | `/api/projects` | Save a project (auth) |

Example:

```bash
curl -s https://prd.haaviq.dev/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"name":"Habit Tracker","desc":"Track habits with streaks","type":"Mobile app"}'
```

## Run locally

```bash
cp .env.example .env      # fill in your keys
pip install -r requirements.txt
uvicorn server:app --reload --port 8789
```

Then open http://127.0.0.1:8789

## Configuration

All configuration is via environment variables (see `.env.example`):

- `AI_BASE_URL`, `AI_API_KEY`, `AI_MODELS` - the generation model
- `PUBLIC_URL` - the public origin, used for OAuth callbacks
- `SESSION_SECRET` - long random string for session cookies
- `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` - GitHub OAuth app

## Deploy

```bash
docker compose up -d --build
```

The app listens on port 8789. Put it behind a reverse proxy with TLS for
public use.

## License

Proprietary. (c) 2026 PRD Studio.
