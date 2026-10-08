# جواب (Replisto)

**هیچ پیامی بی‌جواب نمی‌مونه.** ادمین هوشمند فروشگاه‌های آنلاین: با اطلاعات و محصولات هر فروشگاه به مشتری‌ها در **تلگرام** و **بله** (و بعد از تأیید متا، **اینستاگرام**) جواب می‌دهد و هر جا لازم باشد گفتگو را به صاحب فروشگاه می‌سپارد. صاحب فروشگاه محصولاتش را هر جور راحت است یاد می‌دهد (متن، فایل، عکس، لینک گوگل، پست کانال) و هزینه را به اندازه‌ی مصرف از کیف پولش می‌دهد.

- `backend/`: پایتون (FastAPI)
- `frontend/`: پنل فروشگاه (React + TypeScript)

- **راهنمای کامل فرانت‌اند (برای علی):** [docs/FRONTEND.md](docs/FRONTEND.md)
- **پنل (فرانت‌اند):** [frontend/](frontend/README.md)
- **اسکیمای API:** [docs/openapi.json](docs/openapi.json)
- **برنامه‌ی کانال‌های جدید (واتس‌اپ، تلگرام، بله):** [docs/channels-plan.md](docs/channels-plan.md)
- **راهنمای اجرایی راه‌اندازی (دامنه، متا، سرور، اولین تست واقعی):** [docs/setup-guide.html](docs/setup-guide.html) — [نسخه‌ی آنلاین](https://claude.ai/artifact/Y8e2fe5JsHpLCkxrBHz8Y1)
- **نقشه‌ی لانچ (کارهای بیرون از کد، قدم‌به‌قدم):** [docs/launch-guide.html](docs/launch-guide.html) — فایل را دانلود و در مرورگر باز کنید، یا [نسخه‌ی آنلاین](https://claude.ai/artifact/MjudMjNEeSQR3Yze5A3BXn)

## اجرای کل پروژه روی کامپیوتر خودتان (بک‌اند + پنل)

پیش‌نیاز: [uv](https://docs.astral.sh/uv/) و [Node.js 20+](https://nodejs.org/). به Docker، Redis، اینستاگرام یا کلید هوش مصنوعی نیاز نیست.

۱. فایل `backend/.env` را مثل بخش «اجرای محلی» پایین بسازید. بعد:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_demo
uv run uvicorn app.main:app --reload
```

۲. در یک ترمینال دیگر:

```bash
cd frontend
npm install
npm run dev
```

۳. پنل را در `http://localhost:3000` باز کنید و با `demo@shop.ir` / `demopass123` وارد شوید.

۴. دایرکت مشتری را شبیه‌سازی کنید (باید در بخش «ارجاع‌شده به شما» پنل ظاهر شود):

```bash
cd backend
uv run python -m scripts.simulate dm --text "سلام" --text "فاکتور رسمی میدید؟"
```

### تست هوش مصنوعی واقعی

سه مقدار `LLM_BASE_URL`، `LLM_API_KEY` و `LLM_MODEL` را در `backend/.env` بگذارید (راهنما: قدم ۱.۳ نقشه‌ی لانچ)، بعد:

```bash
cd backend
uv run python -m scripts.check_llm --price-in 0.10 --price-out 0.50
```

سه سناریوی واقعی (سوال محصول، سوال از اطلاعات فروشگاه، سوالی که باید به مدیر ارجاع شود) را اجرا می‌کند و هزینه‌ی هر جواب را تخمین می‌زند.

## ساختار

```
backend/
  app/
    core/        تنظیمات، دیتابیس، امنیت (JWT، هش رمز، رمزنگاری توکن‌ها)
    models/      جداول دیتابیس
    schemas/     مدل‌های ورودی/خروجی API
    api/routes/  endpointها
    services/    منطق اصلی: اینستاگرام، webhook، پیام‌ها، هوش مصنوعی، اطلاعات، محصولات
    worker.py    پردازش پس‌زمینه (arq + Redis)
  alembic/       migrationهای دیتابیس
  scripts/       شبیه‌ساز دایرکت، داده‌ی نمونه، خروجی OpenAPI
  tests/
frontend/          پنل فروشگاه (React + TypeScript + Vite) — frontend/README.md
deploy/            Caddyfile (HTTPS خودکار) و web.Dockerfile (ساخت پنل)
docker-compose.yml
```

## اجرای محلی (بدون Docker)

پیش‌نیاز: [uv](https://docs.astral.sh/uv/)

```bash
cd backend
uv sync
```

برای توسعه‌ی محلی می‌شود به جای Postgres از SQLite استفاده کرد. یک فایل `backend/.env` بسازید:

```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
SECRET_KEY=dev-secret-key-at-least-32-characters-long
ENCRYPTION_KEY=<خروجی دستور زیر>
QUEUE_BACKEND=inline
INSTAGRAM_DRY_RUN=true
META_APP_SECRET=local-secret
```

- `QUEUE_BACKEND=inline`: کارهای پس‌زمینه داخل خود سرور اجرا می‌شوند و Redis لازم نیست (فقط برای توسعه).
- `INSTAGRAM_DRY_RUN=true`: جواب ربات به جای ارسال به اینستاگرام در لاگ سرور چاپ می‌شود.
- روی ویندوز اگر متن فارسی در لاگ به شکل `\u0633...` دیده شد، قبل از اجرای سرور متغیر محیطی `PYTHONUTF8=1` را در ترمینال تنظیم کنید.

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```bash
uv run alembic upgrade head
```

```bash
uv run uvicorn app.main:app --reload
```

مستندات تعاملی API (برای علی): http://localhost:8000/docs

برای داشتن یک فروشگاه نمونه‌ی پر (ورود با `demo@shop.ir` / `demopass123`):

```bash
uv run python -m scripts.seed_demo
```

برای فعال کردن هوش مصنوعی، این سه مقدار را به `.env` اضافه کنید (هر سرویس سازگار با OpenAI که از tool calling پشتیبانی کند):

```
LLM_BASE_URL=https://...
LLM_API_KEY=...
LLM_MODEL=...
```

### شبیه‌سازی دایرکت بدون متا

تا وقتی اپ متا آماده نشده، این اسکریپت نقش اینستاگرام را بازی می‌کند. اینستاگرام فعلا خاموش است؛ برای این تست در `backend/.env` بنویسید `INSTAGRAM_ENABLED=true`. اول در `/docs` یک کاربر ثبت‌نام کنید، بعد:

```bash
uv run python -m scripts.simulate link --email owner@shop.ir
```

```bash
uv run python -m scripts.simulate dm --text "سلام" --text "این مانتو" --text "سایز ۴۴ داره؟"
```

```bash
uv run python -m scripts.simulate dm --echo --text "بله عزیزم موجوده"
```

دستور اول یک پیج اینستاگرام ساختگی به فروشگاه وصل و ربات را روشن می‌کند. دومی سه پیام پشت‌سرهم از طرف مشتری می‌فرستد (ربات فقط **یک** جواب می‌دهد). سومی یعنی صاحب پیج خودش جواب داده و ربات برای آن مشتری ساکت می‌شود.

### تست ربات تلگرام روی کامپیوتر خودتان

1. در تلگرام به @BotFather پیام بدهید، `/newbot` را بزنید و توکن ربات را بگیرید.
2. در `backend/.env` بنویسید `TELEGRAM_BOT_TOKEN=<توکن>` (و برای اینکه کیف پول خالی جلوی تست را نگیرد، `BILLING_ENABLED=false`).
3. بک‌اند را اجرا کنید، و در یک ترمینال دیگر (اگر تلگرام فیلتر است با VPN روشن):

```bash
uv run python -m scripts.telegram_poll
```

این اسکریپت بدون نیاز به سرور عمومی پیام‌های ربات را می‌گیرد و با همان کد سرور جواب می‌دهد. از پنل، بخش تلگرام، حساب خودتان را وصل کنید و لینک فروشگاه (`t.me/<ربات>?start=s_<slug>`) را برای تست به‌عنوان مشتری باز کنید.

### ربات بله

بله همان ربات تلگرام است روی پیام‌رسان داخلی (API بله با تلگرام سازگار است):

1. در اپ بله به `@botfather` پیام بدهید، `/newbot` بزنید و توکن را بگیرید.
2. در `backend/.env` بنویسید `BALE_BOT_TOKEN=<توکن>`.
3. اسکریپت `telegram_poll` را دوباره اجرا کنید؛ هر دو ربات (تلگرام و بله) را با هم اجرا می‌کند.

در پنل، صفحه‌ی «تلگرام و بله»، لینک فروشگاه در بله و دکمه‌ی «وصل کردن بله‌ی خودتان» اضافه می‌شود. پست‌های کانال و «تلگرام بیزینس» فقط در تلگرام هستند (بله آن‌ها را به ربات نمی‌دهد).

### هدیه‌ی شروع کار، تأیید ایمیل و شماره
- ثبت‌نام به‌تنهایی اعتباری نمی‌دهد. هدیه (`SIGNUP_CREDIT_RIAL`، پیش‌فرض ۵۰ هزار تومان) وقتی داده می‌شود که صاحب فروشگاه اکانت تلگرام یا بله‌اش را وصل کند و (اگر `SIGNUP_GIFT_REQUIRES_PHONE=true`) شماره موبایلش را تأیید کند. هر اکانت تلگرام/بله و هر شماره فقط یک بار هدیه می‌گیرد (`gift_claims`، به صورت هش، حتی بعد از حذف حساب).
- شماره موبایل دو راه تأیید دارد: پیامک از پنل (صفحه‌ی حساب کاربری) یا دکمه‌ی «📱 تأیید شماره موبایل» در ربات (اشتراک‌گذاری شماره‌ی خود اکانت؛ رایگان).
- بدون `SMS_PROVIDER` کد پیامک فقط در لاگ API نوشته می‌شود؛ بدون `SMTP_HOST` لینک تأیید ایمیل هم همین‌طور.
- ورود: بعد از ۵ رمز اشتباه برای یک ایمیل (یا ۲۰ از یک IP) در ۱۵ دقیقه، ورود موقتا بسته می‌شود.

### درگاه پرداخت: آبان گیت‌وی

شارژ کیف پول با [آبان گیت‌وی](https://abangateway.ir) است: کارت‌به‌کارت با تأیید خودکار از روی پیامک بانک، بدون اینماد. صاحب فروشگاه مبلغ را می‌زند، به صفحه‌ی پرداخت آبان می‌رود، دقیقا همان مبلغ نمایش‌داده‌شده را کارت‌به‌کارت می‌کند و چند ثانیه بعد آبان با وبهوک امضاشده خبر می‌دهد و کیف پول شارژ می‌شود (`/api/v1/billing/aban/webhook`). اگر وبهوکی گم شود، worker هر ۱۰ دقیقه پرداخت‌های معلق را از آبان می‌پرسد.

- در پنل آبان: کارت را ثبت کنید، کیف پول کارمزد را شارژ کنید، توکن API و کلید مخفی وبهوک بسازید و در `.env` بگذارید (`ABAN_API_TOKEN`، `ABAN_WEBHOOK_SECRET`).
- برای تست بدون پول، توکن `ag_test_` بگذارید و در پنل آبان «شبیه‌سازی پرداخت» را بزنید. آدرس وبهوک باید HTTPS عمومی باشد (روی کامپیوتر خودتان با تونل).
- زرین‌پال هم هست: `PAYMENT_GATEWAY=zarinpal`.

### پنل مدیریت تیم داخل ربات تلگرام (/ops)

شناسه‌ی عددی تلگرام خودتان و علی را (از @userinfobot) در `OPS_ADMIN_TELEGRAM_IDS` بگذارید. بعد در ربات مشترک Replisto (@ReplistoAppBot) دستور `/ops` را بفرستید:

- 🏠 **خانه:** فروشگاه‌ها، پیام‌رسان‌های وصل، هدیه‌ها، پیام‌های امروز، ارجاع‌های باز، شارژ و مصرف امروز و ۳۰ روز، مجموع موجودی‌ها، پرداخت‌های معلق
- 🏪 **فروشگاه‌ها:** تازه‌ترین، پرمصرف‌ترین، کم‌موجودی؛ کارت هر فروشگاه با همه‌ی جزئیات
- روی هر فروشگاه: ➕ شارژ دستی، ➖ کسر، 📜 تراکنش‌ها، ✉️ پیام به صاحب، ⛔️ تعلیق یا رفع تعلیق (همه با تأیید و ثبت در دفتر کیف پول)
- 🔍 **جستجو** با ایمیل، اسم، کد فروشگاه یا شماره
- 💳 **پرداخت‌ها**، 📈 **روند ۷ روز**، 📣 **پیام به همه‌ی صاحبان فروشگاه**، ⚙️ **وضعیت سیستم**

ثبت‌نام‌های تازه و پرداخت‌ها هم به گروه `OPS_TELEGRAM_CHAT_ID` (یا اگر نباشد، به همین افراد) خبر داده می‌شوند.

### کیف پول دستی

شارژ دستی از پنل `/ops` ربات، یا با اسکریپت:

```bash
uv run python -m scripts.wallet credit owner@shop.ir 200000 "کارت به کارت"
```

## تست

```bash
uv run pytest
```

## دیپلوی روی سرور

```bash
cp .env.example .env
```

مقادیر `.env` را پر کنید (راهنمای هر مقدار داخل فایل هست) و رکورد DNS هر دو دامنه‌ی `API_DOMAIN` و `PANEL_DOMAIN` را به IP سرور بزنید، بعد:

```bash
docker compose up -d --build
```

این دستور همه‌چیز را بالا می‌آورد: دیتابیس، Redis، بک‌اند، worker، سرویس `web` (پنل ساخته‌شده از `frontend/` + HTTPS خودکار برای هر دو دامنه با Caddy) و `backup` (پشتیبان‌گیری خودکار از دیتابیس در `./backups`؛ بازگردانی: [deploy/backup/RESTORE.md](deploy/backup/RESTORE.md)). Migrationها موقع بالا آمدن `api` خودکار اجرا می‌شوند، و وبهوک ربات تلگرام هم خودکار روی همین سرور تنظیم می‌شود.

خطاها: با `SENTRY_DSN` به Sentry می‌روند و با `OPS_TELEGRAM_CHAT_ID` همان لحظه در یک چت تلگرام تیم هم اطلاع داده می‌شوند (همان چت نسخه‌ی رمزشده‌ی پشتیبان‌ها را هم می‌گیرد).

شارژ دستی کیف پول روی سرور:

```bash
docker compose exec api python -m scripts.wallet credit owner@shop.ir 200000 "کارت به کارت"
```

به‌روزرسانی بعد از هر push:

```bash
git pull && docker compose up -d --build
```

راهنمای کامل و قدم‌به‌قدم: [docs/setup-guide.html](docs/setup-guide.html).

## قرارداد API برای فرانت

کامل در [docs/FRONTEND.md](docs/FRONTEND.md).
