"""Verifying the owner's mobile number.

An SMS code from the panel (Kavenegar or SMS.ir, with a code template approved in their
panel; without a provider the code is only logged, for development) ends in `user.phone` +
`user.phone_verified_at`.

A number can be verified on one account only (it also limits the sign-up gift, see gifts.py).
"""

import logging
import re
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import secret_digest
from app.core.timeutil import as_utc, utcnow
from app.models import User

logger = logging.getLogger(__name__)

MAX_CODE_ATTEMPTS = 5
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_IRAN_MOBILE = re.compile(r"^9\d{9}$")


class PhoneError(Exception):
    """User-facing (Persian) reason."""


def normalize_iran_mobile(raw: str) -> str:
    """'۰۹۱۲ ۳۴۵ ۶۷۸۹', '+98912...', '98912...', '912...' -> '+989123456789'."""
    digits = re.sub(r"\D", "", raw.translate(_PERSIAN_DIGITS))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if not _IRAN_MOBILE.match(digits):
        raise PhoneError("شماره موبایل درست نیست؛ مثل ۰۹۱۲۳۴۵۶۷۸۹ بنویسید.")
    return "+98" + digits


def local_format(phone: str) -> str:
    """'+989123456789' -> '09123456789' (how Iranians read it)."""
    return "0" + phone[3:] if phone.startswith("+98") else phone


async def owner_of(db: AsyncSession, phone: str) -> User | None:
    return await db.scalar(select(User).where(User.phone == phone))


async def set_verified(db: AsyncSession, user: User, phone: str) -> None:
    """Record a verified number; raises PhoneError if another account already has it."""
    other = await owner_of(db, phone)
    if other is not None and other.id != user.id:
        raise PhoneError("این شماره قبلا برای حساب دیگری در Replisto تأیید شده است.")
    user.phone = phone
    user.phone_verified_at = utcnow()
    user.phone_pending = None
    user.phone_code_hash = None
    user.phone_code_expires_at = None
    user.phone_code_attempts = 0
    await db.commit()


async def start(db: AsyncSession, http: httpx.AsyncClient, user: User, raw: str) -> str:
    """Send a code to this number; returns the normalized number."""
    phone = normalize_iran_mobile(raw)
    other = await owner_of(db, phone)
    if other is not None and other.id != user.id:
        raise PhoneError("این شماره قبلا برای حساب دیگری در Replisto تأیید شده است.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await send_code(http, phone, code)
    settings = get_settings()
    user.phone_pending = phone
    user.phone_code_hash = secret_digest(f"phone:{user.id}:{phone}:{code}")
    user.phone_code_expires_at = utcnow() + timedelta(minutes=settings.phone_code_minutes)
    user.phone_code_attempts = 0
    await db.commit()
    return phone


async def confirm(db: AsyncSession, user: User, code: str) -> str:
    """Check the typed code; on success the pending number becomes the verified one."""
    phone = user.phone_pending
    expires = user.phone_code_expires_at
    if not phone or not user.phone_code_hash or expires is None or as_utc(expires) < utcnow():
        raise PhoneError("کد منقضی شده است؛ دوباره درخواست کد بدهید.")
    if user.phone_code_attempts >= MAX_CODE_ATTEMPTS:
        raise PhoneError("چند بار کد اشتباه وارد شد؛ دوباره درخواست کد بدهید.")
    code = re.sub(r"\D", "", code.translate(_PERSIAN_DIGITS))
    if not secrets.compare_digest(
        user.phone_code_hash, secret_digest(f"phone:{user.id}:{phone}:{code}")
    ):
        user.phone_code_attempts += 1
        await db.commit()
        raise PhoneError("کد درست نیست.")
    await set_verified(db, user, phone)
    return phone


async def send_code(http: httpx.AsyncClient, phone: str, code: str) -> None:
    settings = get_settings()
    provider = settings.sms_provider.strip().lower()
    if not provider:
        logger.info("SMS not sent (SMS_PROVIDER is empty): code %s for %s", code, phone)
        return
    try:
        if provider == "kavenegar":
            resp = await http.post(
                f"https://api.kavenegar.com/v1/{settings.sms_api_key}/verify/lookup.json",
                data={
                    "receptor": local_format(phone),
                    "token": code,
                    "template": settings.sms_template,
                },
                timeout=15,
            )
            ok = resp.status_code == 200
        elif provider == "smsir":
            resp = await http.post(
                "https://api.sms.ir/v1/send/verify",
                headers={"X-API-KEY": settings.sms_api_key, "Accept": "application/json"},
                json={
                    "mobile": local_format(phone),
                    "templateId": int(settings.sms_template),
                    "parameters": [{"name": "CODE", "value": code}],
                },
                timeout=15,
            )
            ok = resp.status_code == 200 and resp.json().get("status") == 1
        else:
            raise PhoneError("ارسال پیامک روی سرور درست تنظیم نشده است.")
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("SMS to %s failed: %s", phone, exc)
        raise PhoneError("ارسال پیامک ممکن نشد؛ چند دقیقه‌ی دیگر دوباره امتحان کنید.") from exc
    if not ok:
        logger.error("SMS provider refused (HTTP %s): %s", resp.status_code, resp.text[:300])
        raise PhoneError("ارسال پیامک ممکن نشد؛ چند دقیقه‌ی دیگر دوباره امتحان کنید.")
