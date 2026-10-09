# Replisto

**No customer goes unanswered.** Replisto is an AI assistant for online shops on Instagram: it answers customers' direct messages, story replies and comments using each shop's own information and products, and hands the conversation to the owner whenever it should. It also publishes the stories the owner schedules and reads the page's insights, with an AI content assistant that turns them into ideas, captions and a weekly plan. Owners teach it their products any way they like (text, files, photos, a Google link or a live Google Sheet) and pay for what they use from a prepaid wallet.

Replisto launches in **Lebanon**: prices in US dollars (or lira), wallet top-ups by Whish Money or OMT, Lebanese mobile numbers, Lebanese law in the terms and privacy policy, and a bot that answers Lebanese Arabic, Arabizi ("kifak, 3endkon...?"), French and English in the language and script the customer uses.

The panel is in English by default, with Arabic (right-to-left) selectable from the language switch. Everything the owner reads follows that choice: the panel, the server's messages and emails, and what the bot writes for the owner (handoff reasons, summaries of what it learned). The panel sends its language with every request (`Accept-Language`) and keeps the shop's `language` in sync.

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

   Open http://localhost:3000 and log in with `demo@shop.com` / `demopass123`. Seed with `--language ar` for an owner who uses the panel in Arabic.

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

A comment under a post (the caption tells the bot which product "how much?" is about):

```bash
uv run python -m scripts.simulate comment --text "How much is this?" --caption "Linen dress, \$49.90"
```

With `INSTAGRAM_DRY_RUN=true` nothing reaches Instagram: replies, private replies and published stories are logged instead.

## Instagram: messages, comments, stories and insights

The Meta app uses the **Instagram API with Instagram Login** and asks for five permissions, each with a screen in the panel that shows it at work:

| Permission | What it's for | Panel |
| --- | --- | --- |
| `instagram_business_basic` | the account's profile and posts | Instagram |
| `instagram_business_manage_messages` | answering DMs, story replies and story mentions | Inbox, Waiting for you |
| `instagram_business_manage_comments` | answering comments publicly or by private reply, hiding spam | Comments |
| `instagram_business_content_publish` | publishing the stories the owner schedules | Stories |
| `instagram_business_manage_insights` | the page's numbers and the content assistant | Insights |

In the App Dashboard, subscribe the webhook to the **messages** and **comments** fields. Accounts connected before a permission existed see a "Reconnect" button on the page that needs it.

- **Comments.** Each shop chooses how the bot answers: under the comment, by private message to the commenter, or both (the answer by DM and a short public note). What the shop's information doesn't cover gets **no reply**: it waits in the panel, sorted by category (price, stock, ordering, complaint...). Emoji-only praise gets a heart without an AI call; friends tagging friends are skipped; spam can be hidden automatically. A private reply also lands in the commenter's DM thread, so the bot keeps the context when they answer there. "Try a comment" in the panel shows what the bot would do, without posting or charging.
- **Stories.** The owner uploads a photo (converted to JPEG) or an MP4/MOV video and picks a time; the worker publishes due stories every minute. Instagram downloads the file from an unguessable URL under `PUBLIC_BASE_URL/api/v1/media/`, so the API must be reachable over HTTPS; files live in `MEDIA_DIR` (a Docker volume) and are deleted 30 days after publishing. The owner's note about each story is what the bot reads when someone replies to it.
- **Insights.** Read daily (and on demand): profile counts, this week against last week, 30-day reach and new followers, and every recent post's numbers. The panel shows what works (format, best days and hours in the owner's time zone, hashtags, top posts). The content assistant's report and chat are paid from the wallet like any answer.

## Wallet and payments

- Every AI answer is charged to the shop's wallet in US cents, by the tokens it used, rounded up to a cent with a minimum per answer (`USAGE_*` settings). `BILLING_ENABLED=false` charges nothing.
- In Lebanon owners top up with a **Whish Money** or **OMT** transfer: set `WHISH_ACCOUNT` / `OMT_ACCOUNT` (the account they send to). The owner enters the amount and the transfer reference in the panel; the payment waits until the team checks it (`OPS_EMAIL` is told about each one):

  ```bash
  uv run python -m scripts.wallet pending
  uv run python -m scripts.wallet approve <payment-id>
  uv run python -m scripts.wallet reject <payment-id> "Not received"
  ```

- Card top-ups through **Stripe Checkout** are optional: Stripe doesn't accept businesses registered in Lebanon, so use it only with a company in a Stripe country. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, and add a webhook endpoint at `https://<api domain>/api/v1/billing/stripe/webhook` listening to the `checkout.session.*` events.
- Credit a wallet by hand (support, refunds):

  ```bash
  uv run python -m scripts.wallet credit owner@shop.com 20 "Support credit"
  ```

## Verification and the welcome gift

- Signing up alone earns nothing. The welcome gift (`SIGNUP_CREDIT_CENTS`, $5 by default) is given once the owner verifies a mobile number, once per number (kept as a keyed hash in `gift_claims`, even after the account is deleted).
- Mobile numbers are stored in E.164 form. Lebanese numbers can be typed as people write them (`70 123 456`, `03 123 456`); other countries need their code (`DEFAULT_PHONE_COUNTRY_CODE`, 961 by default). Codes are sent with **Twilio** (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`), in the owner's language. Without Twilio the code is only written to the API log; without `SMTP_HOST` the email links are too.
- Logging in is blocked for a while after 5 wrong passwords for one email (or 20 from one IP) within 15 minutes.

## Off-topic questions

A message that doesn't obviously look like a shopping question (no words like price, size, stock, *adde*, *قديش*, *combien*, or a product name) first goes through a small, cheap AI check. If it's unrelated to the shop (weather, homework, jokes), the customer gets a short reply in their own language and script ("I can only help with our products…"), with no full AI answer and **no charge to the shop**. After two in a row the bot stays quiet, without any AI call, until the customer asks about the shop again. Settings: `OFF_TOPIC_*`, and `LLM_TRIAGE_MODEL` for a cheaper model for the check.

## "Ask Replisto" on the website

Replisto's own shop answers visitors' questions about Replisto with the same bot: in the "Try it" section of the home page, and in the panel (a floating button on desktop, the "Ask about Replisto" page in the menu on phones). Create it once:

```bash
uv run python -m scripts.seed_house --email team@example.com
```

- If the account doesn't exist it is created and its password printed once. Log in with it to edit what the assistant knows; its chats appear in that account's inbox, questions it can't answer are emailed to it, and the team's reply appears in the visitor's chat window.
- Prices come live from the server's settings. It isn't charged to any wallet.
- **Anti-spam:** a daily token allowance per guest, per logged-in user, per IP and for all guests together (`SITE_CHAT_*`), at most 6 messages a minute and 600 characters a message. The allowance left is shown as a ring next to the chat; a guest who runs out is invited to create a free account.

## Email

Owners get emails with a button (right-to-left in Arabic) to confirm their address, to reset their password, when a customer is waiting for them and when their wallet runs low or out (`EMAIL_ALERTS`). Without `SMTP_HOST` emails are only written to the API log. Check the settings with:

```bash
uv run python -m scripts.send_test_email you@example.com
```

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

On a fresh Ubuntu/Debian server, as root, one script does everything below (installs Docker, downloads the code to `/opt/replisto`, writes `.env` with fresh secrets and starts it); run it again to update:

```bash
bash deploy/setup-server.sh example.com
```

By hand:

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
    core/        settings, database, security (JWT, password hashing, token encryption),
                 i18n.py (server text in English and Arabic)
    models/      database tables
    schemas/     API input/output models
    api/routes/  endpoints
    services/    the core: Instagram, webhooks, messaging, comments, stories, insights, AI,
                 knowledge, products, billing
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
