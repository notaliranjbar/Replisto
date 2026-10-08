import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, SignedInUser
from app.core.config import get_settings
from app.core.security import (
    TokenError,
    create_email_verify_token,
    create_password_reset_token,
    create_token,
    decode_token,
    email_token_matches,
    hash_password,
    read_email_verify_token,
    read_password_reset_token,
    reset_token_matches,
    verify_password,
)
from app.core.throttle import Throttle, minutes_text
from app.core.timeutil import utcnow
from app.models import Shop, User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.services.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# One reset email per address per minute, so the endpoint can't be used to spam someone.
_RESET_INTERVAL_SECONDS = 60
_last_reset_request: dict[str, float] = {}
# Wrong passwords, per email and per IP (an IP may be shared, e.g. an office, so it gets more).
_login_failures_email = Throttle(5, 15 * 60)
_login_failures_ip = Throttle(20, 15 * 60)
# Verification emails: one per minute and five per day per account.
_verify_email_minute = Throttle(1, 60)
_verify_email_day = Throttle(5, 24 * 3600)


def configure_login_throttle() -> None:
    """Apply LOGIN_MAX_FAILURES / LOGIN_FAILURE_WINDOW_MINUTES (and reset the counters)."""
    settings = get_settings()
    window = settings.login_failure_window_minutes * 60
    for throttle, limit in (
        (_login_failures_email, settings.login_max_failures),
        (_login_failures_ip, settings.login_max_failures * 4),
    ):
        throttle.limit = limit
        throttle.window = window
        throttle.clear()


configure_login_throttle()


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2000)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2000)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordOut(BaseModel):
    message: str


def _tokens_for(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> TokenPair:
    email_taken = HTTPException(status.HTTP_409_CONFLICT, "This email is already registered")
    if await db.scalar(select(User.id).where(User.email == body.email)):
        raise email_taken

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
    )
    user.shop = Shop(name=body.shop_name.strip())
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # concurrent registration with the same email
        await db.rollback()
        raise email_taken from None
    # No credit yet: the sign-up gift comes after verifying a phone number (services/gifts.py).
    await _send_verification(user)
    logger.info("new sign-up: shop %s", user.shop.id)
    return _tokens_for(user)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    ip = _client_ip(request)
    for throttle, key in ((_login_failures_email, body.email), (_login_failures_ip, ip)):
        if throttle.blocked(key):
            wait = minutes_text(throttle.retry_after(key))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many wrong passwords. Try again in {wait}, or use “Forgot password”.",
            )
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        _login_failures_email.hit(body.email)
        _login_failures_ip.hit(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    _login_failures_email.reset(body.email)
    return _tokens_for(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbSession) -> TokenPair:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        user_id = decode_token(body.refresh_token, "refresh")
    except TokenError:
        raise invalid from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise invalid
    return _tokens_for(user)


@router.post(
    "/password/forgot", response_model=ForgotPasswordOut, status_code=status.HTTP_202_ACCEPTED
)
async def forgot_password(body: ForgotPasswordRequest, db: DbSession) -> ForgotPasswordOut:
    """Email a password reset link. Same answer whether or not the email is registered,
    so the endpoint doesn't reveal who has an account."""
    answer = ForgotPasswordOut(
        message="If this email is registered with Replisto, a password reset link is on its way."
    )
    now = time.monotonic()
    if now - _last_reset_request.get(body.email, -_RESET_INTERVAL_SECONDS) < (
        _RESET_INTERVAL_SECONDS
    ):
        return answer
    _last_reset_request[body.email] = now

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not user.is_active:
        return answer
    settings = get_settings()
    token = create_password_reset_token(user.id, user.password_hash)
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    try:
        await send_email(
            user.email,
            "Reset your Replisto password",
            "Hi,\n\nOpen this link to choose a new password:\n"
            f"{link}\n\n"
            f"The link works once, for {settings.password_reset_minutes} minutes. "
            "If you didn't ask for this, you can ignore this email.\n\nReplisto",
        )
    except Exception:
        logger.exception("could not send password reset email")
    return answer


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordRequest, db: DbSession) -> None:
    invalid = HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "This reset link is invalid or has expired. Please ask for a new one.",
    )
    try:
        user_id, fingerprint = read_password_reset_token(body.token)
    except TokenError:
        raise invalid from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise invalid
    if not reset_token_matches(fingerprint, user.password_hash):
        raise invalid  # already used: the password changed since the link was made
    user.password_hash = hash_password(body.new_password)
    await db.commit()


async def _send_verification(user: User) -> None:
    settings = get_settings()
    token = create_email_verify_token(user.id, user.email)
    link = f"{settings.frontend_url.rstrip('/')}/verify-email?token={token}"
    try:
        await send_email(
            user.email,
            "Confirm your Replisto email",
            "Hi,\n\nWelcome to Replisto! Open this link to confirm your email:\n"
            f"{link}\n\n"
            f"The link works for {settings.email_verify_days} days. If you didn't sign up "
            "for Replisto, you can ignore this email.\n\nReplisto",
        )
    except Exception:
        logger.exception("could not send the verification email")


@router.post("/email/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(body: VerifyEmailRequest, db: DbSession) -> None:
    """The link from the verification email (the panel's /verify-email page calls this)."""
    invalid = HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "This confirmation link is invalid or has expired. Ask for a new one from the panel.",
    )
    try:
        user_id, fingerprint = read_email_verify_token(body.token)
    except TokenError:
        raise invalid from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active or not email_token_matches(fingerprint, user.email):
        raise invalid
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        await db.commit()


@router.post("/email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(user: SignedInUser) -> ForgotPasswordOut:
    if user.email_verified_at is not None:
        return ForgotPasswordOut(message="Your email is already confirmed.")
    key = str(user.id)
    for throttle in (_verify_email_minute, _verify_email_day):
        if throttle.blocked(key):
            wait = minutes_text(throttle.retry_after(key))
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Please try again in {wait}.")
    _verify_email_minute.hit(key)
    _verify_email_day.hit(key)
    await _send_verification(user)
    return ForgotPasswordOut(message=f"A confirmation link was sent to {user.email}.")
