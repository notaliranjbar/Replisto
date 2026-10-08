# پنل Replisto (فرانت‌اند)

React + TypeScript + Vite، با TanStack Query برای درخواست‌ها و Tailwind برای استایل. کل پنل RTL است و نسخه‌ی انگلیسی هم دارد (برای داور متا).
قرارداد API و رفتار هر صفحه: [docs/FRONTEND.md](../docs/FRONTEND.md)

## اجرا

پیش‌نیاز: Node 20+ و بک‌اند در حال اجرا روی `http://localhost:8000` (بخش ۱ از FRONTEND.md).

```bash
cd frontend
npm install
```

```bash
npm run dev
```

پنل روی `http://localhost:3000` باز می‌شود (همان `FRONTEND_URL` پیش‌فرض بک‌اند). ورود نمونه: `demo@shop.ir` / `demopass123`

## تنظیمات

یک فایل `frontend/.env` از روی `.env.example` بسازید:

| متغیر | توضیح |
|---|---|
| `VITE_API_URL` | آدرس بک‌اند، پیش‌فرض `http://localhost:8000` |
| `VITE_SUPPORT_EMAIL` | ایمیل تماس در صفحه‌های `/privacy`، `/terms` و `/data-deletion` (برای تأیید متا لازم است) |

## دستورها

| دستور | کار |
|---|---|
| `npm run dev` | اجرای محلی |
| `npm run build` | بررسی تایپ‌ها + ساخت نسخه‌ی نهایی در `dist/` |
| `npm run gen:api` | ساخت دوباره‌ی `src/api/schema.d.ts` از `docs/openapi.json` (بعد از هر تغییر API) |

## ساختار

```
src/
  api/         client.ts (توکن و refresh خودکار)، schema.d.ts (خودکار)، types.ts، queries.ts
  auth/        وضعیت ورود
  i18n/        fa.ts (زبان اصلی)، en.ts (باید هم‌شکل fa باشد)، sections.ts
  lib/         قالب‌بندی تاریخ شمسی و اعداد، خطاها، اعلان مرورگر
  components/  Layout (منو، badgeها، عنوان تب)، اجزای UI، فرم FAQ، اجزای گفتگو
  pages/       یک فایل برای هر صفحه؛ public/Legal.tsx صفحه‌های عمومی متا
```

## دیپلوی

خروجی `npm run build` یک SPA ایستا است. سرور باید همه‌ی مسیرها (مثل `/instagram/callback`) را به `index.html` برگرداند.
در Caddy:

```
app.replisto.app {
	root * /srv/panel
	try_files {path} /index.html
	file_server
}
```

`FRONTEND_URL` و `CORS_ORIGINS` بک‌اند باید آدرس همین پنل باشند.
