"""The wallet: pay-as-you-go answers, an empty wallet, and top-ups through Stripe."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import (
    Conversation,
    InstagramAccount,
    Message,
    MessageSender,
    Payment,
    PaymentStatus,
    Shop,
    User,
    WalletEntry,
    WalletEntryKind,
)
from app.services import billing, payments
from app.services.messaging import reply_to_conversation
from app.services.responder import Reply
from tests.conftest import FakeMeta, FakeWeb


class TokenResponder:
    calls = 0

    async def generate(self, shop: Shop, history: list, **_: object) -> Reply:
        TokenResponder.calls += 1
        return Reply(text="Yes, it's in stock", prompt_tokens=4000, completion_tokens=150)


class RecordingNotifier:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def handoff(self, shop: Shop, conversation: Conversation) -> None:
        self.events.append("handoff")

    async def wallet_low(self, shop: Shop) -> None:
        self.events.append("low")

    async def wallet_empty(self, shop: Shop) -> None:
        self.events.append("empty")

    async def message(self, shop: Shop, text: str, keyboard=None) -> None:
        self.events.append(text)


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    user = User(email="owner@shop.com", password_hash="x")
    user.shop = Shop(
        name="Boutique",
        bot_enabled=True,
        fallback_message="A teammate will reply soon",
        balance_cents=1000,
    )
    db.add(user)
    await db.flush()
    db.add(
        InstagramAccount(
            shop_id=user.shop.id,
            ig_user_id="1",
            username="s",
            access_token_encrypted=encrypt_secret("t"),
        )
    )
    await db.commit()
    return user.shop


async def _customer_asks(db: AsyncSession, shop: Shop) -> Conversation:
    conversation = Conversation(
        shop_id=shop.id, customer_id="c1", last_customer_message_at=utcnow()
    )
    db.add(conversation)
    await db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.CUSTOMER,
            text="Is it in stock?",
            external_id=f"m-{uuid.uuid4()}",
        )
    )
    await db.commit()
    return conversation


async def _reply(db, conversation, fake_meta, notifier) -> None:  # type: ignore[no-untyped-def]
    await reply_to_conversation(
        db,
        conversation.id,
        as_utc(conversation.last_customer_message_at),
        fake_meta.client(),
        TokenResponder(),
        notifier=notifier,
    )


def test_usage_cost() -> None:
    # 100k prompt tokens * 0.05 + 10k completion * 0.2, per 1000 = 7 cents
    assert billing.usage_cost(100_000, 10_000) == 7
    # 4000 * 0.05 + 150 * 0.2 = 0.23 cents, rounded up to a cent
    assert billing.usage_cost(4000, 150) == 1
    assert billing.usage_cost(10, 5) == get_settings().usage_min_cents_per_reply


async def test_answer_is_paid_from_the_wallet(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta, billing_on: None
) -> None:
    notifier = RecordingNotifier()
    await _reply(db, await _customer_asks(db, shop), fake_meta, notifier)
    assert len(fake_meta.sent) == 1
    [entry] = (await db.scalars(select(WalletEntry))).all()
    assert entry.kind == WalletEntryKind.USAGE
    assert entry.amount_cents == -1 and entry.balance_after_cents == 999
    assert entry.details["prompt_tokens"] == 4000
    await db.refresh(shop)
    assert shop.balance_cents == 999
    assert notifier.events == []


async def test_low_balance_is_announced_once(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta, billing_on: None
) -> None:
    shop.balance_cents = get_settings().low_balance_cents + 1
    await db.commit()
    notifier = RecordingNotifier()
    await _reply(db, await _customer_asks(db, shop), fake_meta, notifier)
    await _reply(db, await _customer_asks_again(db, shop), fake_meta, notifier)
    assert notifier.events == ["low"]


async def _customer_asks_again(db: AsyncSession, shop: Shop) -> Conversation:
    conversation = Conversation(
        shop_id=shop.id, customer_id=f"c-{uuid.uuid4()}", last_customer_message_at=utcnow()
    )
    db.add(conversation)
    await db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.CUSTOMER,
            text="?",
            external_id=f"m-{uuid.uuid4()}",
        )
    )
    await db.commit()
    return conversation


async def test_empty_wallet_hands_off_without_calling_the_ai(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta, billing_on: None
) -> None:
    shop.balance_cents = 0
    await db.commit()
    notifier = RecordingNotifier()
    TokenResponder.calls = 0
    conversation = await _customer_asks(db, shop)
    await _reply(db, conversation, fake_meta, notifier)

    assert TokenResponder.calls == 0
    assert [m["message"]["text"] for m in fake_meta.sent] == ["A teammate will reply soon"]
    await db.refresh(conversation)
    assert conversation.handoff_open
    assert notifier.events == ["handoff", "empty"]
    assert (await db.scalars(select(WalletEntry))).all() == []


async def test_billing_off_charges_nothing(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta
) -> None:
    shop.balance_cents = 0
    await db.commit()
    await _reply(db, await _customer_asks(db, shop), fake_meta, RecordingNotifier())
    assert [m["message"]["text"] for m in fake_meta.sent] == ["Yes, it's in stock"]


async def test_signing_up_alone_earns_no_gift(client: AsyncClient, billing_on: None) -> None:
    """The gift waits for a verified phone number (test_verification.py)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@shop.com", "password": "strongpass1", "shop_name": "S"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    body = (await client.get("/api/v1/billing", headers=headers)).json()
    assert body["balance_cents"] == 0
    entries = (await client.get("/api/v1/billing/entries", headers=headers)).json()
    assert entries["items"] == []
    gift = (await client.get("/api/v1/dashboard", headers=headers)).json()["wallet"]["gift"]
    assert gift == {
        "amount_cents": get_settings().signup_credit_cents,
        "granted": False,
        "phone_verified": False,
    }


WEBHOOK_SECRET = "whsec_test"


@pytest.fixture
def stripe_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_key")
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", WEBHOOK_SECRET)


def _signed(event: dict, at: int | None = None) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(event).encode()
    stamp = str(at if at is not None else int(time.time()))
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), stamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return raw, {
        "Stripe-Signature": f"t={stamp},v1={signature}",
        "Content-Type": "application/json",
    }


def _event(kind: str, session_id: str) -> dict:
    return {"type": kind, "data": {"object": {"id": session_id, "object": "checkout.session"}}}


async def _balance(client: AsyncClient, headers: dict) -> int:
    return (await client.get("/api/v1/billing", headers=headers)).json()["balance_cents"]


async def _topup(client: AsyncClient, headers: dict, cents: int = 2000):  # type: ignore[no-untyped-def]
    return await client.post("/api/v1/billing/topup", json={"amount_cents": cents}, headers=headers)


async def test_topup_needs_stripe_and_a_valid_amount(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
    billing_on: None,
) -> None:
    resp = await _topup(client, auth_headers)
    assert resp.status_code == 400  # Stripe not configured yet
    assert not (await client.get("/api/v1/billing", headers=auth_headers)).json()["topup_available"]

    monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_key")
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", WEBHOOK_SECRET)
    resp = await _topup(client, auth_headers, cents=100)
    assert resp.status_code == 400 and "between $5.00 and $1,000.00" in resp.json()["detail"]


async def test_stripe_topup_by_webhook(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, stripe_on: None, billing_on: None
) -> None:
    billing_info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert billing_info["gateway"] == "stripe" and billing_info["topup_available"]
    resp = await _topup(client, auth_headers)
    assert resp.status_code == 200, resp.text
    session_id = f"cs_test_{1:060d}"
    assert resp.json()["payment_url"] == f"https://checkout.stripe.com/c/pay/{session_id}"
    created = fake_web.stripe.created[0]
    assert created["line_items[0][price_data][unit_amount]"] == "2000"
    assert created["line_items[0][price_data][currency]"] == "usd"
    assert created["success_url"].startswith("https://api.test/api/v1/billing/stripe/return/")
    assert created["cancel_url"].endswith("?cancelled=1")

    raw, headers = _signed(_event("checkout.session.completed", session_id))
    # A forged call (wrong signature) is refused and credits nothing.
    forged = await client.post(
        "/api/v1/billing/stripe/webhook",
        content=raw,
        headers={**headers, "Stripe-Signature": "t=1,v1=00"},
    )
    assert forged.status_code == 400
    # A replayed old event is refused too.
    old_raw, old_headers = _signed(_event("checkout.session.completed", session_id), at=1)
    resp = await client.post("/api/v1/billing/stripe/webhook", content=old_raw, headers=old_headers)
    assert resp.status_code == 400

    # Signed, but Stripe says it isn't paid: nothing is credited.
    resp = await client.post("/api/v1/billing/stripe/webhook", content=raw, headers=headers)
    assert resp.status_code == 200
    assert await _balance(client, auth_headers) == 0

    fake_web.stripe.pay(session_id)
    resp = await client.post("/api/v1/billing/stripe/webhook", content=raw, headers=headers)
    assert resp.status_code == 200
    assert await _balance(client, auth_headers) == 2000
    # Delivered again (Stripe retries): credited once only.
    await client.post("/api/v1/billing/stripe/webhook", content=raw, headers=headers)
    assert await _balance(client, auth_headers) == 2000
    entries = (await client.get("/api/v1/billing/entries", headers=auth_headers)).json()
    assert [(e["kind"], e["amount_cents"]) for e in entries["items"]] == [("topup", 2000)]


async def test_stripe_return_cancel_and_reconcile(
    client: AsyncClient,
    auth_headers: dict,
    fake_web: FakeWeb,
    db: AsyncSession,
    stripe_on: None,
    billing_on: None,
) -> None:
    resp = await _topup(client, auth_headers)
    assert resp.status_code == 200
    payment = await db.scalar(select(Payment))
    assert payment is not None and payment.session_id == f"cs_test_{1:060d}"
    back = f"/api/v1/billing/stripe/return/{payment.id}"

    # Back from checkout before Stripe confirmed: "pending".
    resp = await client.get(back)
    assert resp.headers["location"] == "https://panel.test/billing?payment=pending"

    # The webhook got lost; the periodic check finds the paid session.
    fake_web.stripe.pay(payment.session_id)
    payment.created_at = utcnow() - timedelta(minutes=10)
    await db.commit()
    credited = await payments.reconcile(db, payments.Stripe(fake_web.client()))
    assert [p.id for p in credited] == [payment.id]
    resp = await client.get(back)
    assert resp.headers["location"] == "https://panel.test/billing?payment=success"
    assert await _balance(client, auth_headers) == 2000

    # Cancelled on the checkout page.
    await _topup(client, auth_headers)
    second = await db.scalar(select(Payment).where(Payment.id != payment.id))
    assert second is not None
    resp = await client.get(f"/api/v1/billing/stripe/return/{second.id}?cancelled=1")
    assert resp.headers["location"] == "https://panel.test/billing?payment=failed"

    # An expired session becomes a failed payment.
    await _topup(client, auth_headers)
    third = f"cs_test_{3:060d}"
    fake_web.stripe.expire(third)
    raw, headers = _signed(_event("checkout.session.expired", third))
    await client.post("/api/v1/billing/stripe/webhook", content=raw, headers=headers)
    db.expire_all()
    statuses = sorted(p.status.value for p in (await db.scalars(select(Payment))).all())
    assert statuses == [
        PaymentStatus.FAILED.value,
        PaymentStatus.FAILED.value,
        PaymentStatus.PAID.value,
    ]
    assert await _balance(client, auth_headers) == 2000


async def test_stripe_refusal_is_explained(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, stripe_on: None, billing_on: None
) -> None:
    fake_web.stripe.create_error = (503, "api_error")
    resp = await _topup(client, auth_headers)
    assert resp.status_code == 400 and "try again" in resp.json()["detail"]
