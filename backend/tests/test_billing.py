"""The wallet: pay-as-you-go answers, an empty wallet, and top-ups (Aban, Zarinpal)."""

import hashlib
import hmac
import json
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
        return Reply(text="بله موجوده", prompt_tokens=4000, completion_tokens=150)


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
    user = User(email="owner@shop.ir", password_hash="x")
    user.shop = Shop(
        name="مزون", bot_enabled=True, fallback_message="همکارم جواب میده", balance_rial=200_000
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
            text="موجوده؟",
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
    # 4000 prompt tokens * 300 + 150 completion * 1200, per 1000 = 1380 rial
    assert billing.usage_cost(4000, 150) == 1380
    assert billing.usage_cost(10, 5) == get_settings().usage_min_rial_per_reply


async def test_answer_is_paid_from_the_wallet(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta, billing_on: None
) -> None:
    notifier = RecordingNotifier()
    await _reply(db, await _customer_asks(db, shop), fake_meta, notifier)
    assert len(fake_meta.sent) == 1
    [entry] = (await db.scalars(select(WalletEntry))).all()
    assert entry.kind == WalletEntryKind.USAGE
    assert entry.amount_rial == -1380 and entry.balance_after_rial == 200_000 - 1380
    assert entry.details["prompt_tokens"] == 4000
    await db.refresh(shop)
    assert shop.balance_rial == 200_000 - 1380
    assert notifier.events == []


async def test_low_balance_is_announced_once(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta, billing_on: None
) -> None:
    shop.balance_rial = get_settings().low_balance_rial + 1000
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
    shop.balance_rial = 0
    await db.commit()
    notifier = RecordingNotifier()
    TokenResponder.calls = 0
    conversation = await _customer_asks(db, shop)
    await _reply(db, conversation, fake_meta, notifier)

    assert TokenResponder.calls == 0
    assert [m["message"]["text"] for m in fake_meta.sent] == ["همکارم جواب میده"]
    await db.refresh(conversation)
    assert conversation.handoff_open
    assert notifier.events == ["handoff", "empty"]
    assert (await db.scalars(select(WalletEntry))).all() == []


async def test_billing_off_charges_nothing(
    db: AsyncSession, shop: Shop, fake_meta: FakeMeta
) -> None:
    shop.balance_rial = 0
    await db.commit()
    await _reply(db, await _customer_asks(db, shop), fake_meta, RecordingNotifier())
    assert [m["message"]["text"] for m in fake_meta.sent] == ["بله موجوده"]


async def test_signing_up_alone_earns_no_gift(client: AsyncClient, billing_on: None) -> None:
    """The gift waits for a verified phone number (test_verification.py)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@shop.ir", "password": "strongpass1", "shop_name": "S"},
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    body = (await client.get("/api/v1/billing", headers=headers)).json()
    assert body["balance_toman"] == 0
    entries = (await client.get("/api/v1/billing/entries", headers=headers)).json()
    assert entries["items"] == []
    gift = (await client.get("/api/v1/dashboard", headers=headers)).json()["wallet"]["gift"]
    assert gift == {
        "amount_toman": get_settings().signup_credit_rial // 10,
        "granted": False,
        "phone_verified": False,
    }


async def test_zarinpal_topup(
    client: AsyncClient,
    auth_headers: dict,
    fake_web: FakeWeb,
    monkeypatch: pytest.MonkeyPatch,
    billing_on: None,
) -> None:
    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    assert resp.status_code == 400  # gateway not configured yet

    monkeypatch.setattr(get_settings(), "payment_gateway", "zarinpal")
    monkeypatch.setattr(get_settings(), "zarinpal_merchant_id", "merchant-1")
    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    url = resp.json()["payment_url"]
    assert url.startswith("https://sandbox.zarinpal.com/pg/StartPay/A")
    assert fake_web.zarinpal.requests[0]["amount"] == 1_000_000  # rial
    authority = url.rsplit("/", 1)[1]

    callback = "/api/v1/billing/zarinpal/callback"
    resp = await client.get(callback, params={"Authority": authority, "Status": "OK"})
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://panel.test/billing?payment=success&ref=201"
    # A second hit (refresh) doesn't credit again.
    await client.get(callback, params={"Authority": authority, "Status": "OK"})
    body = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert body["balance_toman"] == 100_000
    assert len(fake_web.zarinpal.verifies) == 1

    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    authority = resp.json()["payment_url"].rsplit("/", 1)[1]
    resp = await client.get(callback, params={"Authority": authority, "Status": "NOK"})
    assert resp.headers["location"].endswith("payment=failed")


WEBHOOK_SECRET = "whsec-test"


@pytest.fixture
def aban_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "aban_api_token", "ag_test_token")
    monkeypatch.setattr(get_settings(), "aban_webhook_secret", WEBHOOK_SECRET)


def _signed(event: dict) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(event).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Signature": signature, "Content-Type": "application/json"}


async def _balance(client: AsyncClient, headers: dict) -> int:
    return (await client.get("/api/v1/billing", headers=headers)).json()["balance_toman"]


async def test_aban_topup_by_webhook(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, aban_on: None, billing_on: None
) -> None:
    billing_info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert billing_info["gateway"] == "aban" and billing_info["topup_available"]
    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_url"] == "https://abangateway.ir/pay/inv_00000000000000000001"
    created = fake_web.aban.created[0]
    assert created["amount_rial"] == 1_000_000
    assert created["callback_url"] == "https://api.test/api/v1/billing/aban/webhook"
    assert created["return_url"].startswith("https://api.test/api/v1/billing/aban/return/")

    event = {"event": "invoice.paid", "invoice_id": "inv_00000000000000000001", "status": "paid"}
    raw, headers = _signed(event)
    # A forged call (wrong signature) is refused and credits nothing.
    forged = await client.post(
        "/api/v1/billing/aban/webhook", content=raw, headers={**headers, "X-Signature": "00"}
    )
    assert forged.status_code == 401

    # Signed, but the money hasn't arrived yet: verify says not paid, nothing is credited.
    resp = await client.post("/api/v1/billing/aban/webhook", content=raw, headers=headers)
    assert resp.status_code == 200
    assert await _balance(client, auth_headers) == 0

    fake_web.aban.pay("inv_00000000000000000001")
    resp = await client.post("/api/v1/billing/aban/webhook", content=raw, headers=headers)
    assert resp.status_code == 200
    assert await _balance(client, auth_headers) == 100_000
    # Delivered again (Aban retries): credited once only.
    await client.post("/api/v1/billing/aban/webhook", content=raw, headers=headers)
    assert await _balance(client, auth_headers) == 100_000
    entries = (await client.get("/api/v1/billing/entries", headers=auth_headers)).json()
    assert [e["kind"] for e in entries["items"]] == ["topup"]


async def test_aban_return_and_reconcile(
    client: AsyncClient,
    auth_headers: dict,
    fake_web: FakeWeb,
    db: AsyncSession,
    aban_on: None,
    billing_on: None,
) -> None:
    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    assert resp.status_code == 200
    payment = await db.scalar(select(Payment))
    assert payment is not None and payment.authority == "inv_00000000000000000001"
    back = f"/api/v1/billing/aban/return/{payment.id}"

    # Back from the payment page before the bank SMS: "pending".
    resp = await client.get(back)
    assert resp.headers["location"] == "https://panel.test/billing?payment=pending"

    # The webhook got lost; the periodic check finds the paid invoice.
    fake_web.aban.pay("inv_00000000000000000001")
    payment.created_at = utcnow() - timedelta(minutes=10)
    await db.commit()
    credited = await payments.reconcile_aban(db, payments.AbanGateway(fake_web.client()))
    assert [p.id for p in credited] == [payment.id]
    resp = await client.get(back)
    assert resp.headers["location"] == "https://panel.test/billing?payment=success"
    assert await _balance(client, auth_headers) == 100_000

    # An expired invoice becomes a failed payment.
    await client.post("/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers)
    raw, headers = _signed({"event": "invoice.expired", "invoice_id": "inv_00000000000000000002"})
    await client.post("/api/v1/billing/aban/webhook", content=raw, headers=headers)
    db.expire_all()
    statuses = sorted(p.status.value for p in (await db.scalars(select(Payment))).all())
    assert statuses == [PaymentStatus.FAILED.value, PaymentStatus.PAID.value]


async def test_aban_refusal_is_explained(
    client: AsyncClient, auth_headers: dict, fake_web: FakeWeb, aban_on: None, billing_on: None
) -> None:
    fake_web.aban.create_error = (503, "capacity_full")
    resp = await client.post(
        "/api/v1/billing/topup", json={"amount_toman": 100_000}, headers=auth_headers
    )
    assert resp.status_code == 400 and "شلوغ" in resp.json()["detail"]
