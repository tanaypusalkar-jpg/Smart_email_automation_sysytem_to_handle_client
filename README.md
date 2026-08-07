# Email Automation System

An AI-powered email backend built with **FastAPI** and the **Claude API**. It classifies incoming
emails, drafts new emails or replies, pulls context from a small **vector store (ChromaDB)** so
drafts match your past style, sends mail over SMTP, and logs everything to a **SQLite database**
for an audit trail. `/emails/send` is rate-limited and can be gated behind **Google OAuth**.

A static showcase website (`/website`) demonstrates the project and calls the live API.

---

## What it does

| Feature | Endpoint | Notes |
|---|---|---|
| Classify an email | `POST /emails/classify` | Category, priority, sentiment + reasoning |
| Draft a new email | `POST /compose` | Optional RAG context pulled from stored templates |
| Draft a reply | `POST /emails/reply` | Classifies + replies in one call |
| Send an email | `POST /emails/send` | Rate-limited, OAuth-gated once configured, SMTP-backed |
| Store a template | `POST /compose/templates` | Adds to the vector store for future retrieval |
| View audit log | `GET /logs` | Recent classify/compose/send activity from the database |
| Health check | `GET /health` | Confirms API keys / SMTP / OAuth config are loaded |

## Project structure

```
email-automation-system/
├── app/
│   ├── main.py              # FastAPI app, CORS, rate limiter, DB init, /health, /logs
│   ├── config.py            # Settings (env vars via pydantic-settings)
│   ├── models.py            # Request/response schemas
│   ├── models_db.py         # SQLAlchemy ORM model (EmailLog)
│   ├── db.py                # DB engine/session setup
│   ├── auth.py               # Google OAuth verification (no-op if unconfigured)
│   ├── rate_limit.py         # Shared slowapi Limiter instance
│   ├── routers/
│   │   ├── emails.py         # classify, reply, send
│   │   └── compose.py        # compose new email, store templates
│   └── services/
│       ├── claude_service.py # All Claude API calls + JSON parsing
│       ├── rag_service.py    # ChromaDB template storage + retrieval
│       ├── email_service.py  # SMTP sending
│       └── log_service.py    # Writes audit log rows
├── tests/test_main.py        # Mocked-Claude tests, temp DB, OAuth off
├── website/                  # Static showcase site
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── render.yaml                # Render.com deploy config
├── pyproject.toml
└── .env.example
```

## Setup (uv, local dev)

```bash
cd email-automation-system
uv sync --extra dev
cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY at minimum

uv run uvicorn app.main:app --reload
# docs at http://127.0.0.1:8000/docs
```

Run tests (mocked Claude calls, temp SQLite DB, no real API key needed):

```bash
uv run pytest -v
```

## The database

SQLite by default, one file at `app/data/emails.db`, created automatically on first run — no
migration step needed for this schema. Every classify / compose / send call writes a row.
Check it via `GET /logs?limit=20` or open the file directly with any SQLite browser.

To move to Postgres later (e.g. your deploy platform gives you a managed Postgres instance),
change one line in `.env`:
```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```
Nothing else in the code changes — that's the point of going through SQLAlchemy instead of
raw file I/O.

**Not included:** Alembic migrations. The schema is one flat table and stable; if you add
columns later, add Alembic then. Don't add migration tooling before you have anything to migrate.

## OAuth on `/emails/send`

Controlled entirely by `GOOGLE_CLIENT_ID` in `.env`:

- **Blank (default):** auth check is skipped. Local dev and tests never need a Google credential.
- **Set:** every call to `/emails/send` must include `Authorization: Bearer <google-id-token>`,
  verified server-side against your Google Cloud OAuth Client ID.

To get a client ID: Google Cloud Console → APIs & Services → Credentials → Create OAuth Client ID
→ Web application → add your deployed domain as an authorized origin.

On the website, add Google Identity Services, get an ID token on sign-in, and send it as a
bearer token with the `/emails/send` fetch call. `/emails/classify` and `/compose` are left
ungated — they're read-only/side-effect-free, gating them would just add friction for no
security benefit.

## Rate limiting

`RATE_LIMIT_SEND` and `RATE_LIMIT_COMPOSE` in `.env` (slowapi syntax, e.g. `5/minute`). This is
IP-based and in-memory — fine for a single-instance deploy, resets if the container restarts.
If you ever run multiple instances behind a load balancer, swap slowapi's storage backend to
Redis so limits are shared across instances.

## Docker

Build and run locally:
```bash
docker build -t email-automation-system .
docker run --env-file .env -p 8000:8000 -v $(pwd)/app/data:/app/app/data email-automation-system
```

Or with Compose (also runs the website on a second port):
```bash
docker compose up --build
```
- API: http://localhost:8000
- Website: http://localhost:8080

The volume mount on `app/data` keeps your SQLite DB and Chroma store across container restarts —
without it, every `docker run` starts with an empty database.

## Deploying (Render)

1. Push this repo to GitHub (check `.env` is NOT in it — see Security below).
2. On Render.com: New → Blueprint → connect the repo. `render.yaml` in this repo defines the
   service already (Docker-based, free tier).
3. In the Render dashboard, set the environment variables under "Environment": `ANTHROPIC_API_KEY`,
   `SMTP_USERNAME`, `SMTP_PASSWORD`, `GOOGLE_CLIENT_ID` (if using OAuth), `DRY_RUN=true` to start.
   Never put these in `render.yaml` itself — that file is committed to the repo.
4. Render gives you a Postgres add-on if you want it — if so, copy its connection string into
   `DATABASE_URL` instead of the SQLite default. Render's free-tier filesystem is ephemeral,
   so SQLite data will NOT survive a redeploy there — use Postgres for anything you want to keep.
5. Deploy the website separately as a Render **Static Site** (or GitHub Pages) pointing at
   `website/`. Update `API_BASE` in `website/script.js` to your deployed API URL — it currently
   points at `127.0.0.1:8000` for local dev.

## Security checklist (do this before/after pushing to GitHub)

- **Check `.env` never got committed.** `git log --all --full-history -- .env` — if it shows up
  anywhere in history, rotate `ANTHROPIC_API_KEY` and your SMTP app password immediately; deleting
  the file in a new commit does not remove it from history.
- **Keep `DRY_RUN=true`** on any public deployment until OAuth is actually configured. Without it,
  anyone with the URL can send real email through your SMTP account.
- **Lock down CORS** in `app/main.py` (`allow_origins`) to your actual deployed website domain
  once you have one — `"*"` is fine for local dev only.
- **Never put API keys in `website/` files.** The frontend has no backend of its own; any key in
  `script.js` is visible to anyone who opens dev tools.
- **Enable GitHub Dependabot alerts** (Settings → Security) — free, flags known-vulnerable
  dependencies in `uv.lock`.
- **Rate limits are your spam brake**, not a nice-to-have — keep `RATE_LIMIT_SEND` tight (5/minute
  or lower) on anything public.

## Known limitations

- Rate limiting is in-memory, per-instance — not shared across multiple running containers.
- No IMAP polling — the system doesn't read a real inbox automatically, you feed it email content
  via the API. That's the natural next step for true end-to-end automation.
- SQLite on most free-tier hosts (Render included) does not persist across redeploys — use
  Postgres if the audit log matters to you in production.

## License

MIT — use it, extend it, put it on your resume.
