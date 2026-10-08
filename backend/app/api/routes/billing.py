"""The shop's wallet (pay as you go) and top-ups through the payment gateway."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import CurrentShop, DbSession, HttpClient
from app.core.config import get_settings
from app.models import Payment, PaymentStatus, WalletEntry, WalletEntryKind
from app.services import billing, payments
from app.services.payments import PaymentError, Stripe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class PricingOut(BaseModel):
    """What usage costs (US cents). An answer costs by the AI tokens it used, with a minimum."""

    per_1k_prompt_tokens_cents: float
    per_1k_completion_tokens_cents: float
    min_per_answer_cents: float
    # A typical answer for a shop with a mid-size catalogue, to set expectations.
    typical_answer_cents: int


class BillingOut(BaseModel):
    # False while billing is switched off on the server (nothing is charged).
    enabled: bool
    balance_cents: int
    low_balance: bool
    pricing: PricingOut
    # Whether online top-up (payment gateway) is available.
    topup_available: bool
    # "stripe"
    gateway: str
    topup_min_cents: int
    topup_max_cents: int


class WalletEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: WalletEntryKind
    amount_cents: int
    balance_after_cents: int
    description: str
    details: dict[str, Any]
    created_at: datetime


class WalletEntryPage(BaseModel):
    items: list[WalletEntryOut]
    total: int


class TopupIn(BaseModel):
    amount_cents: int = Field(gt=0, le=10**9)


class TopupOut(BaseModel):
    # Send the browser here; after paying, the owner comes back to FRONTEND_URL/billing with
    # ?payment=success, ?payment=pending (not confirmed yet) or ?payment=failed.
    payment_url: str


def get_gateway(http: HttpClient) -> Stripe:
    return payments.gateway_for(http)


@router.get("", response_model=BillingOut)
async def get_billing(shop: CurrentShop, http: HttpClient) -> BillingOut:
    settings = get_settings()
    gateway = payments.gateway_for(http)
    return BillingOut(
        enabled=billing.enabled(),
        balance_cents=shop.balance_cents,
        low_balance=billing.enabled() and shop.balance_cents < settings.low_balance_cents,
        pricing=PricingOut(
            per_1k_prompt_tokens_cents=settings.usage_cents_per_1k_prompt_tokens,
            per_1k_completion_tokens_cents=settings.usage_cents_per_1k_completion_tokens,
            min_per_answer_cents=settings.usage_min_cents_per_reply,
            typical_answer_cents=billing.usage_cost(4000, 150),
        ),
        topup_available=gateway.configured,
        gateway=gateway.name,
        topup_min_cents=settings.topup_min_cents,
        topup_max_cents=settings.topup_max_cents,
    )


@router.get("/entries", response_model=WalletEntryPage)
async def list_entries(
    shop: CurrentShop,
    db: DbSession,
    kind: WalletEntryKind | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> WalletEntryPage:
    """The wallet history, newest first."""
    query = select(WalletEntry).where(WalletEntry.shop_id == shop.id)
    if kind is not None:
        query = query.where(WalletEntry.kind == kind)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(
        query.order_by(WalletEntry.created_at.desc()).offset(offset).limit(limit)
    )
    return WalletEntryPage(
        items=[WalletEntryOut.model_validate(e) for e in rows],
        total=total or 0,
    )


@router.post("/topup", response_model=TopupOut)
async def topup(
    body: TopupIn,
    shop: CurrentShop,
    db: DbSession,
    gateway: Stripe = Depends(get_gateway),
) -> TopupOut:
    try:
        url = await payments.start_topup(db, shop, body.amount_cents, gateway)
    except PaymentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return TopupOut(payment_url=url)


def _after_topup(payment: Payment) -> None:
    logger.info("payment %s credited to shop %s", payment.id, payment.shop_id)


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: DbSession,
    gateway: Stripe = Depends(get_gateway),
) -> Response:
    """Stripe reports Checkout Session changes here, signed with our webhook secret."""
    raw = await request.body()
    if not gateway.signature_ok(raw, request.headers.get("stripe-signature", "")):
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    try:
        event = json.loads(raw)
    except ValueError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    if not isinstance(event, dict):
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    try:
        credited = await payments.stripe_webhook(db, event, gateway)
    except PaymentError:
        # Stripe retries; reading the session can succeed then.
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    if credited is not None:
        _after_topup(credited)
    return Response(status_code=status.HTTP_200_OK)


@router.get("/stripe/return/{payment_id}", include_in_schema=False)
async def stripe_return(
    payment_id: uuid.UUID,
    db: DbSession,
    gateway: Stripe = Depends(get_gateway),
    cancelled: bool = False,
) -> RedirectResponse:
    """The owner's browser comes back here from Stripe's checkout page."""
    panel = f"{get_settings().frontend_url.rstrip('/')}/billing"
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.gateway != gateway.name:
        return RedirectResponse(f"{panel}?payment=failed")
    if payment.status == PaymentStatus.PENDING:
        if cancelled:
            payment.status = PaymentStatus.FAILED
            payment.error = "Cancelled on the checkout page."
            await db.commit()
        else:
            try:
                if await payments.settle(db, payment, gateway):
                    _after_topup(payment)
            except PaymentError:
                pass
    if payment.status == PaymentStatus.PAID:
        return RedirectResponse(f"{panel}?payment=success")
    if payment.status == PaymentStatus.PENDING:
        # Some payment methods confirm a little later; the webhook will credit it.
        return RedirectResponse(f"{panel}?payment=pending")
    return RedirectResponse(f"{panel}?payment=failed")
