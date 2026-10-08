# Replisto

**No customer goes unanswered.** Replisto is an AI assistant for online shops: it answers customers' Instagram direct messages using each shop's own information and products, and hands the conversation to the owner whenever it should. Owners teach it their products any way they like (text, files, photos, a Google link or a live Google Sheet) and pay for what they use from a prepaid wallet.

The panel is in English by default, with Arabic (right-to-left) selectable from the language switch. The bot replies to each customer in the language they write in.

- `backend/`: Python (FastAPI, SQLAlchemy, arq)
- `frontend/`: the shop panel and public site (React + TypeScript + Vite + Tailwind)
- API schema: [docs/openapi.json](docs/openapi.json)

## Run everything locally

Prerequisites: [uv](https://docs.astral.sh/uv/) and [Node.js 20+](https://nodejs.org/). Docker, Redis, Instagram and an AI key are not needed.

1. Create `backend/.env`:

   ```
   DATABASE_URL=sqlite+aiosqlite:///./dev.db
   SECRET_KEY=dev-secret-key-at-least-32-characters-long
   ENCRYPTION_KEY=<output of the command below>
   QUEUE_BACKEND=inline
   INSTAGRAM_DRY_RUN=true
   META_APP_SECRET=local-secret
   ```

   ```bash
   cd backend
   uv sync
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   - `QUEUE_BACKEND=inline` runs background jobs inside the API process, so Redis isn't needed (development only).
   - `INSTAGRAM_DRY_RUN=true` writes the bot's replies to the server log instead of sending them to Instagram.

2. Start the API with a demo shop:

   ```bash
   cd backend
   uv run alembic upgrade head
   uv run python -m scripts.seed_demo
   uv run uvicorn app.main:app --reload
   ```

   Interactive API docs: http://localhost:8000/docs

3. In another terminal, start the panel:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Open http://localhost:3000 and log in with `demo@shop.com` / `demopass123`.

### Real AI answers

Add any OpenAI-compatible provider that supports tool calling to `backend/.env`:

```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=...
LLM_MODEL=...
```

Then check the bot on real customer situations (in English and Arabic) without touching your data:

```bash
uv run python -m scripts.check_llm
```

### Simulate Instagram DMs without Meta

This script plays Instagram's part. Register a user (in the panel or at `/docs`), then:

```bash
uv run python -m scripts.simulate link --email owner@shop.com
uv run python -m scripts.simulate dm --text "Hi" --text "this dress" --text "do you have M?"
uv run python -m scripts.simulate dm --echo --text "Yes, it's in stock!"
```

The first command attaches a fake Instagram account to the shop and turns the bot on. The second sends three quick customer messages (the bot answers them **once**). The third acts as the owner replying by hand, which pauses the bot for that customer.

## Wallet and payments

- Every AI answer is charged to the shop's wallet in US cents, by the tokens it used, rounded up to a cent with a minimum per answer (`USAGE_*` settings). `BILLING_ENABLED=false` charges nothing.
- Top-ups go through **Stripe Checkout**. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, and add a webhook endpoint at `https://<api domain>/api/v1/billing/stripe/webhook` listening to the `checkout.session.*` events. The wallet is credited once, after the session is read back from Stripe; the worker also re-checks pending payments every 10 minutes in case a webhook is lost.
- Credit a wallet by hand (support, refunds):

  ```bash
  uv run python -m scripts.wallet credit owner@shop.com 20 "Support credit"
  ```

## Verification and the welcome gift

- Signing up alone earns nothing. The welcome gift (`SIGNUP_CREDIT_CENTS`, $5 by default) is given once the owner verifies a mobile number, once per number (kept as a keyed hash in `gift_claims`, even after the account is deleted).
- Mobile numbers are international (E.164, e.g. `+971501234567`) and codes are sent with **Twilio** (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`). Without Twilio the code is only written to the API log; without `SMTP_HOST` the email links are too.
- Logging in is blocked for a while after 5 wrong passwords for one email (or 20 from one IP) within 15 minutes.

## Tests

```bash
cd backend
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

```bash
cd frontend
npm run build
```

After changing the API, regenerate the schema and the panel's types:

```bash
cd backend && uv run python -m scripts.export_openapi
cd ../frontend && npm run gen:api
```

## Deploy

```bash
cp .env.example .env
```

Fill in `.env` (each value is explained in the file), point DNS records for both `API_DOMAIN` and `PANEL_DOMAIN` at the server, then:

```bash
docker compose up -d --build
```

This starts the database, Redis, the API, the worker, `web` (the panel built from `frontend/`, with automatic HTTPS for both domains through Caddy) and `backup` (automatic database backups into `./backups`; restoring: [deploy/backup/RESTORE.md](deploy/backup/RESTORE.md)). Migrations run automatically when `api` starts. Errors go to Sentry when `SENTRY_DSN` is set.

To update after a push:

```bash
git pull && docker compose up -d --build
```

## Layout

```
backend/
  app/
    core/        settings, database, security (JWT, password hashing, token encryption)
    models/      database tables
    schemas/     API input/output models
    api/routes/  endpoints
    services/    the core: Instagram, webhooks, messaging, AI, knowledge, products, billing
    worker.py    background jobs (arq + Redis)
  alembic/       database migrations
  scripts/       demo data, DM simulator, LLM checks, wallet, OpenAPI export
  tests/
frontend/
  src/
    api/         client (tokens and automatic refresh), generated schema, queries
    i18n/        en.ts / ar.ts (same shape, checked by TypeScript) and page copy
    components/  layout, UI kit, conversation, teaching and site components
    pages/       one file per page; public/Legal.tsx holds the privacy, terms and data-deletion pages
deploy/          Caddyfile (automatic HTTPS), web.Dockerfile (panel build), backups
docker-compose.yml
```
