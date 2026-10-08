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
from app.services.payments import AbanGateway, PaymentError, Zarinpal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class PricingOut(BaseModel):
    """What usage costs (toman). An answer costs by the AI tokens it used, with a minimum."""

    per_1k_prompt_tokens_toman: float
    per_1k_completion_tokens_toman: float
    min_per_answer_toman: float
    # A typical answer for a shop with a mid-size catalogue, to set expectations.
    typical_answer_toman: int


class BillingOut(BaseModel):
    # False while billing is switched off on the server (nothing is charged).
    enabled: bool
    balance_toman: int
    low_balance: bool
    pricing: PricingOut
    # Whether online top-up (payment gateway) is available.
    topup_available: bool
    # "aban" (card-to-card with automatic confirmation) or "zarinpal".
    gateway: str
    topup_min_toman: int
    topup_max_toman: int


class WalletEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: WalletEntryKind
    amount_toman: float
    balance_after_toman: float
    description: str
    details: dict[str, Any]
    created_at: datetime


class WalletEntryPage(BaseModel):
    items: list[WalletEntryOut]
    total: int


class TopupIn(BaseModel):
    amount_toman: int = Field(gt=0, le=10**9)


class TopupOut(BaseModel):
    # Send the browser here; after paying, the owner comes back to FRONTEND_URL/billing with
    # ?payment=success, ?payment=pending (card-to-card not confirmed yet) or ?payment=failed.
    payment_url: str


def get_gateway(http: HttpClient) -> AbanGateway | Zarinpal:
    return payments.gateway_for(http)


def get_zarinpal(http: HttpClient) -> Zarinpal:
    return Zarinpal(http)


def get_aban(http: HttpClient) -> AbanGateway:
    return AbanGateway(http)


@router.get("", response_model=BillingOut)
async def get_billing(shop: CurrentShop, http: HttpClient) -> BillingOut:
    settings = get_settings()
    gateway = payments.gateway_for(http)
    return BillingOut(
        enabled=billing.enabled(),
        balance_toman=shop.balance_rial // 10,
        low_balance=billing.enabled() and shop.balance_rial < settings.low_balance_rial,
        pricing=PricingOut(
            per_1k_prompt_tokens_toman=settings.usage_rial_per_1k_prompt_tokens / 10,
            per_1k_completion_tokens_toman=settings.usage_rial_per_1k_completion_tokens / 10,
            min_per_answer_toman=settings.usage_min_rial_per_reply / 10,
            typical_answer_toman=billing.usage_cost(4000, 150) // 10,
        ),
        topup_available=gateway.configured,
        gateway=gateway.name,
        topup_min_toman=settings.topup_min_rial // 10,
        topup_max_toman=settings.topup_max_rial // 10,
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
        items=[
            WalletEntryOut(
                id=e.id,
                kind=e.kind,
                amount_toman=e.amount_rial / 10,
                balance_after_toman=e.balance_after_rial / 10,
                description=e.description,
                details=e.details,
                created_at=e.created_at,
            )
            for e in rows
        ],
        total=total or 0,
    )


@router.post("/topup", response_model=TopupOut)
async def topup(
    body: TopupIn,
    shop: CurrentShop,
    db: DbSession,
    gateway: AbanGateway | Zarinpal = Depends(get_gateway),
) -> TopupOut:
    try:
        url = await payments.start_topup(db, shop, body.amount_toman * 10, gateway)
    except PaymentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return TopupOut(payment_url=url)


def _after_topup(payment: Payment) -> None:
    logger.info("payment %s credited to shop %s", payment.id, payment.shop_id)


@router.post("/aban/webhook", include_in_schema=False)
async def aban_webhook(
    request: Request,
    db: DbSession,
    gateway: AbanGateway = Depends(get_aban),
) -> Response:
    """Aban Gateway reports invoice changes here, signed with our webhook secret."""
    raw = await request.body()
    if not gateway.signature_ok(raw, request.headers.get("x-signature", "")):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        event = json.loads(raw)
    except ValueError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    if not isinstance(event, dict):
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    try:
        credited = await payments.aban_webhook(db, event, gateway)
    except PaymentError:
        # Aban retries; verifying can succeed then.
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    if credited is not None:
        _after_topup(credited)
    return Response(status_code=status.HTTP_200_OK)


@router.get("/aban/return/{payment_id}", include_in_schema=False)
async def aban_return(
    payment_id: uuid.UUID,
    db: DbSession,
    gateway: AbanGateway = Depends(get_aban),
) -> RedirectResponse:
    """The owner's browser comes back here from Aban's payment page."""
    panel = f"{get_settings().frontend_url.rstrip('/')}/billing"
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.gateway != "aban":
        return RedirectResponse(f"{panel}?payment=failed")
    if payment.status == PaymentStatus.PENDING:
        try:
            if await payments.settle_aban(db, payment, gateway):
                _after_topup(payment)
        except PaymentError:
            pass
    if payment.status == PaymentStatus.PAID:
        return RedirectResponse(f"{panel}?payment=success")
    if payment.status == PaymentStatus.PENDING:
        # Card-to-card: the bank SMS may arrive a little later; the webhook will credit it.
        return RedirectResponse(f"{panel}?payment=pending")
    return RedirectResponse(f"{panel}?payment=failed")


@router.get("/zarinpal/callback", include_in_schema=False)
async def zarinpal_callback(
    db: DbSession,
    gateway: Zarinpal = Depends(get_zarinpal),
    authority: str = Query(alias="Authority", default=""),
    payment_status: str = Query(alias="Status", default=""),
) -> RedirectResponse:
    """Zarinpal sends the owner's browser here after paying; we verify and go to the panel."""
    panel = f"{get_settings().frontend_url.rstrip('/')}/billing"
    was_pending = authority != "" and (
        await db.scalar(select(Payment.status).where(Payment.authority == authority))
        == PaymentStatus.PENDING
    )
    payment = (
        await payments.complete_topup(db, authority, payment_status == "OK", gateway)
        if authority
        else None
    )
    if payment is not None and payment.status.value == "paid":
        if was_pending:
            _after_topup(payment)
        return RedirectResponse(f"{panel}?payment=success&ref={payment.ref_id or ''}")
    return RedirectResponse(f"{panel}?payment=failed")
