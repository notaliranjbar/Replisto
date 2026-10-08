"""Wallet top-ups through Stripe Checkout.

    panel ──POST /billing/topup──► Checkout Session ──► owner pays on Stripe's page
                                                            │
             webhook (checkout.session.*) / owner returns / periodic check
                                                            ▼
                                     read the session from Stripe ──► wallet credited (once)

The webhook is the main path; the return page and the periodic check are safety nets. Each
path reads the session back from Stripe before crediting, so only Stripe's own word counts.

A payment is credited exactly once: it is claimed (status PAID) before crediting.
"""

import hashlib
import hmac
import logging
import time
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.timeutil import utcnow
from app.models import Payment, PaymentStatus, Shop, WalletEntryKind
from app.services import billing

logger = logging.getLogger(__name__)

# Stripe's own recommendation for how old a signed webhook may be.
SIGNATURE_TOLERANCE_SECONDS = 300


class PaymentError(Exception):
    """User-facing reason a payment could not start or complete."""


class StripeError(PaymentError):
    def __init__(self, message: str, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class Stripe:
    name = "stripe"

    def __init__(self, http: httpx.AsyncClient, settings: Settings | None = None) -> None:
        self._http = http
        self._settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self._settings.stripe_secret_key and self._settings.stripe_webhook_secret)

    @property
    def is_test(self) -> bool:
        return self._settings.stripe_secret_key.startswith("sk_test_")

    def signature_ok(self, raw: bytes, header: str, now: float | None = None) -> bool:
        """Check the Stripe-Signature header: "t=<unix time>,v1=<hmac>[,v1=...]".

        The signed payload is "<t>.<raw body>", HMAC-SHA256 with the webhook secret.
        """
        secret = self._settings.stripe_webhook_secret
        if not secret or not header:
            return False
        timestamp = ""
        signatures = []
        for part in header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                signatures.append(value)
        if not timestamp.isdigit() or not signatures:
            return False
        if abs((now if now is not None else time.time()) - int(timestamp)) > (
            SIGNATURE_TOLERANCE_SECONDS
        ):
            return False
        expected = hmac.new(
            secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        return any(hmac.compare_digest(expected, sent) for sent in signatures)

    async def create_session(
        self,
        amount_cents: int,
        payment_id: str,
        success_url: str,
        cancel_url: str,
        description: str,
    ) -> dict[str, Any]:
        return await self._call(
            "POST",
            "/v1/checkout/sessions",
            {
                "mode": "payment",
                "client_reference_id": payment_id,
                "metadata[payment_id]": payment_id,
                "line_items[0][quantity]": "1",
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": str(amount_cents),
                "line_items[0][price_data][product_data][name]": description[:250],
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
            idempotency_key=f"topup-{payment_id}",
        )

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._call("GET", f"/v1/checkout/sessions/{session_id}")

    async def _call(
        self,
        method: str,
        path: str,
        form: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        url = self._settings.stripe_api_base.rstrip("/") + path
        headers = {"Authorization": f"Bearer {self._settings.stripe_secret_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            resp = await self._http.request(method, url, data=form, headers=headers, timeout=20)
        except httpx.HTTPError as exc:
            raise StripeError(
                "Couldn't reach the payment provider. Please try again in a moment."
            ) from exc
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        if resp.status_code < 400 and isinstance(data, dict):
            return data
        error = data.get("error") if isinstance(data, dict) else None
        code = str(error.get("code") or error.get("type") or "") if isinstance(error, dict) else ""
        if resp.status_code in (401, 403):
            logger.error("Stripe refused %s %s: HTTP %s %s", method, path, resp.status_code, data)
        else:
            logger.warning("Stripe %s %s: HTTP %s %s", method, path, resp.status_code, data)
        raise StripeError(
            "The payment provider isn't available right now. Please try again in a moment.",
            code=code,
            status=resp.status_code,
        )


def _api_url(path: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/billing/{path}"


def gateway_for(http: httpx.AsyncClient) -> Stripe:
    """The gateway this server takes top-ups with."""
    return Stripe(http)


def _check_amount(amount_cents: int) -> None:
    settings = get_settings()
    if not settings.topup_min_cents <= amount_cents <= settings.topup_max_cents:
        raise PaymentError(
            f"The top-up amount must be between {billing.usd(settings.topup_min_cents)} and "
            f"{billing.usd(settings.topup_max_cents)}."
        )


async def start_topup(db: AsyncSession, shop: Shop, amount_cents: int, gateway: Stripe) -> str:
    """Create a pending payment; returns the Checkout URL to send the owner to."""
    if not gateway.configured:
        raise PaymentError("Online payments aren't set up yet. Please contact support.")
    _check_amount(amount_cents)
    payment = Payment(shop_id=shop.id, gateway=gateway.name, amount_cents=amount_cents)
    db.add(payment)
    await db.commit()
    back = _api_url(f"stripe/return/{payment.id}")
    try:
        session = await gateway.create_session(
            amount_cents,
            payment_id=str(payment.id),
            success_url=back,
            cancel_url=f"{back}?cancelled=1",
            description=f"Replisto wallet top-up - {shop.name}",
        )
    except PaymentError as exc:
        payment.status = PaymentStatus.FAILED
        payment.error = str(exc)
        await db.commit()
        raise
    payment.session_id = str(session.get("id") or "")[:255] or None
    await db.commit()
    url = session.get("url")
    if not payment.session_id or not url:
        raise PaymentError("The payment provider sent an unexpected answer. Please try again.")
    return str(url)


async def _credit(db: AsyncSession, payment: Payment, ref_id: str | None) -> bool:
    """Mark paid and credit the wallet; False if another request already did."""
    if payment.status == PaymentStatus.PAID:
        return False
    # Claim the payment before crediting, so a parallel request can't credit it twice.
    payment.status = PaymentStatus.PAID
    payment.ref_id = (ref_id or "")[:255] or None
    payment.paid_at = utcnow()
    payment.error = None
    await db.commit()
    shop = await db.get(Shop, payment.shop_id)
    if shop is not None:
        await billing.apply(
            db,
            shop,
            payment.amount_cents,
            WalletEntryKind.TOPUP,
            "Wallet top-up",
            {"payment_id": str(payment.id), "gateway": payment.gateway, "ref_id": payment.ref_id},
        )
    return True


async def _fail(db: AsyncSession, payment: Payment, reason: str) -> None:
    payment.status = PaymentStatus.FAILED
    payment.error = reason
    await db.commit()


async def settle(db: AsyncSession, payment: Payment, gateway: Stripe) -> bool:
    """Read the payment's session from Stripe and act on it. True if credited now."""
    if payment.status != PaymentStatus.PENDING or not payment.session_id:
        return False
    try:
        session = await gateway.get_session(payment.session_id)
    except StripeError as exc:
        if exc.status == 404:
            await _fail(db, payment, "The checkout session no longer exists.")
        else:
            logger.warning("stripe lookup failed for payment %s: %s", payment.id, exc.code)
        return False
    if session.get("amount_total") not in (None, payment.amount_cents) or (
        str(session.get("currency") or "usd").lower() != "usd"
    ):
        logger.error("stripe session %s doesn't match payment %s", payment.session_id, payment.id)
        await _fail(db, payment, "The paid amount didn't match the top-up.")
        return False
    if session.get("payment_status") in ("paid", "no_payment_required"):
        return await _credit(db, payment, str(session.get("payment_intent") or ""))
    if session.get("status") == "expired":
        await _fail(db, payment, "The checkout session expired.")
    return False


async def stripe_webhook(
    db: AsyncSession, event: dict[str, Any], gateway: Stripe
) -> Payment | None:
    """A signed event from Stripe (the caller checked the signature). Idempotent.

    Returns the payment if this call credited it, else None.
    """
    kind = str(event.get("type") or "")
    if not kind.startswith("checkout.session."):
        return None
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    session_id = str(obj.get("id") or "") if isinstance(obj, dict) else ""
    if not session_id:
        return None
    payment = await db.scalar(
        select(Payment).where(Payment.gateway == gateway.name, Payment.session_id == session_id)
    )
    if payment is None or payment.status != PaymentStatus.PENDING:
        return None
    if kind == "checkout.session.async_payment_failed":
        await _fail(db, payment, "The payment failed.")
        return None
    return payment if await settle(db, payment, gateway) else None


async def reconcile(db: AsyncSession, gateway: Stripe) -> list[Payment]:
    """Safety net for lost webhooks: settle pending payments from the last two days.

    Returns the payments credited now.
    """
    if not gateway.configured:
        return []
    now = utcnow()
    pending = (
        await db.scalars(
            select(Payment).where(
                Payment.gateway == gateway.name,
                Payment.status == PaymentStatus.PENDING,
                Payment.session_id.is_not(None),
                Payment.created_at > now - timedelta(days=2),
                Payment.created_at < now - timedelta(minutes=2),
            )
        )
    ).all()
    return [payment for payment in pending if await settle(db, payment, gateway)]
