"""Verifying the owner's mobile number.

An SMS code from the panel (sent through Twilio; without a Twilio account the code is only
logged, for development) ends in `user.phone` + `user.phone_verified_at`.

Numbers are kept in E.164 form (+96170123456). A number typed without a country code
("70 123 456", "03 123 456") is taken to be in DEFAULT_PHONE_COUNTRY_CODE (Lebanon, 961).
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
from app.core.i18n import tr
from app.core.security import secret_digest
from app.core.text import to_ascii_digits
from app.core.timeutil import as_utc, utcnow
from app.models import User

logger = logging.getLogger(__name__)

MAX_CODE_ATTEMPTS = 5
# E.164: a country code and number, 8 to 15 digits in all, never starting with 0.
_E164 = re.compile(r"^[1-9]\d{7,14}$")
# Lebanese mobiles: 3 + 6 digits (03 ...), or 70/71/76/78/79/81 + 6 digits.
_LEBANESE_MOBILE = re.compile(r"^961(3\d{6}|(70|71|76|78|79|81)\d{6})$")
_INVALID = "Enter a valid mobile number, like 70 123 456 or +961 70 123 456."


class PhoneError(Exception):
    """User-facing reason."""


def normalize(raw: str) -> str:
    """'70 123 456', '03 123 456', '+961 70 123 456' or '00961...' -> '+96170123456'.

    Other countries need their code ('+1 415 555 0123'). Arabic-Indic digits work too.
    """
    text = to_ascii_digits(raw).strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits:
        # A local number: the country code of the market we serve, without the trunk 0.
        digits = get_settings().default_phone_country_code + digits.lstrip("0")
    lebanese = digits.startswith("961")
    if not _E164.match(digits) or (lebanese and not _LEBANESE_MOBILE.match(digits)):
        raise PhoneError(_INVALID)
    return "+" + digits


async def owner_of(db: AsyncSession, phone: str) -> User | None:
    return await db.scalar(select(User).where(User.phone == phone))


async def set_verified(db: AsyncSession, user: User, phone: str) -> None:
    """Record a verified number; raises PhoneError if another account already has it."""
    other = await owner_of(db, phone)
    if other is not None and other.id != user.id:
        raise PhoneError("This number is already verified on another Replisto account.")
    user.phone = phone
    user.phone_verified_at = utcnow()
    user.phone_pending = None
    user.phone_code_hash = None
    user.phone_code_expires_at = None
    user.phone_code_attempts = 0
    await db.commit()


async def start(db: AsyncSession, http: httpx.AsyncClient, user: User, raw: str) -> str:
    """Send a code to this number; returns the normalized number."""
    phone = normalize(raw)
    other = await owner_of(db, phone)
    if other is not None and other.id != user.id:
        raise PhoneError("This number is already verified on another Replisto account.")
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
        raise PhoneError("The code has expired. Please ask for a new one.")
    if user.phone_code_attempts >= MAX_CODE_ATTEMPTS:
        raise PhoneError("Too many wrong codes. Please ask for a new one.")
    code = re.sub(r"\D", "", to_ascii_digits(code))
    if not secrets.compare_digest(
        user.phone_code_hash, secret_digest(f"phone:{user.id}:{phone}:{code}")
    ):
        user.phone_code_attempts += 1
        await db.commit()
        raise PhoneError("That code isn't right.")
    await set_verified(db, user, phone)
    return phone


async def send_code(http: httpx.AsyncClient, phone: str, code: str) -> None:
    settings = get_settings()
    if not settings.twilio_account_sid:
        logger.info("SMS not sent (TWILIO_ACCOUNT_SID is empty): code %s for %s", code, phone)
        return
    sender = settings.twilio_from.strip()
    form = {
        "To": phone,
        "Body": tr("Your {app} verification code is {code}", app=settings.app_name, code=code),
        # A Messaging Service picks the best sender per country.
        ("MessagingServiceSid" if sender.startswith("MG") else "From"): sender,
    }
    url = (
        f"{settings.twilio_api_base.rstrip('/')}/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )
    try:
        resp = await http.post(
            url,
            data=form,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=15,
        )
    except httpx.HTTPError as exc:
        logger.error("SMS to %s failed: %s", phone, exc)
        raise PhoneError(
            "We couldn't send the text message. Please try again in a few minutes."
        ) from exc
    if resp.status_code >= 400:
        logger.error("Twilio refused (HTTP %s): %s", resp.status_code, resp.text[:300])
        raise PhoneError(
            "We couldn't send a text message to this number. Check it and try again."
            if resp.status_code == 400
            else "We couldn't send the text message. Please try again in a few minutes."
        )
