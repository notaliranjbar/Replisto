"""Text reaches the owner in their panel's language (English or Arabic)."""

import ast
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import i18n
from app.core.config import get_settings
from app.core.i18n import AR, localize, tr
from app.models import Shop, TeachProposal
from app.services import teach
from app.services.llm import LLMClient
from app.services.responder import ChatTurn, LLMResponder
from tests.conftest import FakeWeb

AR_HEADERS = {"Accept-Language": "ar-LB,ar;q=0.9,en;q=0.8"}
APP = Path(__file__).resolve().parents[1] / "app"

# Errors whose message the owner reads.
_USER_ERRORS = {
    "PhoneError",
    "PaymentError",
    "StripeError",
    "TeachError",
    "ExtractionError",
    "ProductSourceError",
    "StoryError",
    "InsightsError",
}
# Messages only machines read (Meta's webhook calls, the health check).
_INTERNAL_FILES = {"webhooks.py", "health.py"}


def _constant(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _template(node: ast.expr) -> str | None:
    """An f-string as the template localize() matches: values become {placeholders}."""
    if not isinstance(node, ast.JoinedStr):
        return _constant(node)
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        else:
            parts.append("{x}")
    return "".join(parts)


def _user_messages() -> list[tuple[str, str]]:
    found = []
    for path in APP.rglob("*.py"):
        if path.name in _INTERNAL_FILES or path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            name = node.func.id
            if name == "tr" and node.args:
                text = _constant(node.args[0])
            elif name in _USER_ERRORS and node.args:
                text = _template(node.args[0])
            elif name == "HTTPException" and len(node.args) > 1:
                text = _template(node.args[1])
            else:
                continue
            if text:
                found.append((f"{path.name}:{node.lineno}", text))
    return found


def test_every_message_has_an_arabic_translation() -> None:
    templates = [(i18n._PLACEHOLDER.sub("{x}", key), key) for key in AR]
    missing = [
        (where, text)
        for where, text in _user_messages()
        if text not in AR and text not in {t for t, _ in templates}
    ]
    assert missing == []


def test_translating_text_with_values() -> None:
    assert (
        tr("Please try again in {wait}.", "ar", wait="3 دقائق")
        == "يرجى المحاولة مجددًا بعد 3 دقائق."
    )
    # Text produced in English earlier, values and all.
    assert localize("The table has 2,500 rows, over the limit of 2000.", "ar") == (
        "يحتوي الجدول على 2,500 صفًا، وهذا أكثر من الحد المسموح (2000)."
    )
    assert localize("Welcome gift", "ar") == "هدية البداية"
    assert localize("Welcome gift", "en") == "Welcome gift"
    assert localize("Something we never wrote", "ar") == "Something we never wrote"
    assert localize("2 products added.\nUndone.", "ar").endswith("تم التراجع.")
    assert [i18n.minutes(n, "ar") for n in (1, 2, 5, 15)] == [
        "دقيقة واحدة",
        "دقيقتين",
        "5 دقائق",
        "15 دقيقة",
    ]
    assert i18n.language_from_header("fr-LB,ar;q=0.8") == "ar"
    assert i18n.language_from_header("fr") == "en"


async def test_errors_come_in_the_panels_language(client: AsyncClient) -> None:
    wrong = {"email": "nobody@shop.com", "password": "wrongpass1"}
    resp = await client.post("/api/v1/auth/login", json=wrong, headers=AR_HEADERS)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "البريد الإلكتروني أو كلمة المرور غير صحيحة"
    resp = await client.post("/api/v1/auth/login", json=wrong)
    assert resp.json()["detail"] == "Wrong email or password"


async def test_signing_up_in_arabic(client: AsyncClient, db: AsyncSession) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "rita@shop.com", "password": "strongpass1", "shop_name": "Rita"},
        headers=AR_HEADERS,
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}", **AR_HEADERS}
    shop = (await client.get("/api/v1/shop", headers=headers)).json()
    # The shop starts in Arabic, with an Arabic handoff message for customers.
    assert shop["language"] == "ar"
    assert shop["fallback_message"].startswith("شكرًا")
    # The panel switches the language when the owner does.
    resp = await client.patch("/api/v1/shop", json={"language": "en"}, headers=headers)
    assert resp.json()["language"] == "en"


async def test_emails_in_the_owners_language(
    client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes import auth

    sent: list[tuple[str, str, str]] = []

    async def fake_send(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        sent.append((to, subject, body))

    monkeypatch.setattr(auth, "send_email", fake_send)
    resp = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "owner@shop.com"}, headers=AR_HEADERS
    )
    assert "Replisto" in resp.json()["message"] and "إعادة تعيين" in resp.json()["message"]
    [(_, subject, body)] = sent
    assert subject == "إعادة تعيين كلمة مرور Replisto"
    assert "https://panel.test/reset-password?token=" in body and "دقيقة" in body


async def test_handoff_reasons_in_the_owners_language(
    db: AsyncSession, fake_web: FakeWeb, llm_on: None
) -> None:
    shop = Shop(owner_id=uuid.uuid4(), name="Boutique", language="ar")
    db.add(shop)
    await db.commit()
    fake_web.llm_replies = [{"content": "Hi"}]
    await LLMResponder(LLMClient(fake_web.client()), db).generate(
        shop, [ChatTurn("customer", "Hi")]
    )
    [handoff] = [
        t for t in fake_web.llm_requests[0]["tools"] if t["function"]["name"] == "handoff_to_human"
    ]
    reason = handoff["function"]["parameters"]["properties"]["reason"]["description"]
    assert "in Arabic" in reason and "العميل يريد فاتورة رسمية" in reason
    # Lebanese customers: Arabizi, Lebanese Arabic and French get answered in kind.
    system = fake_web.llm_requests[0]["messages"][0]["content"]
    assert "Arabizi" in system and "French" in system


async def test_wallet_history_in_arabic(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, billing_on: None
) -> None:
    from app.models import WalletEntryKind
    from app.services import billing

    shop = await db.scalar(select(Shop))
    assert shop is not None
    await billing.apply(db, shop, 500, WalletEntryKind.BONUS, "Welcome gift")
    entries = (
        await client.get("/api/v1/billing/entries", headers={**auth_headers, **AR_HEADERS})
    ).json()
    assert entries["items"][0]["description"] == "هدية البداية"


def test_teach_preview_in_arabic() -> None:
    proposal = TeachProposal(
        summary="",
        changes={
            "products": [
                {
                    "action": "update",
                    "product_id": "x",
                    "before": {"name": "Dress", "price": 40},
                    "fields": {"price": 45, "stock": 2},
                    "locked": False,
                }
            ],
            "knowledge": [],
            "questions": [],
        },
    )
    i18n.set_language("ar")
    try:
        preview = teach.describe(proposal)
        result = teach.describe_result(
            {"created": 2, "updated": 0, "deleted": 0, "knowledge": 1, "locked": 0, "skipped": 0}
        )
    finally:
        i18n.set_language("en")
    assert "السعر: 40 → 45" in preview and "المخزون: - → 2" in preview
    assert result == "أُضيف 2 منتجات؛ حُفظ عنصر واحد في معلومات المتجر."


# ---------------------------------------------------------------------------- transfers


@pytest.fixture
def transfers_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "whish_account", "70 123 456")
    monkeypatch.setattr(get_settings(), "omt_account", "Replisto SAL, 03 123 456")


async def test_whish_transfer_is_credited_once_approved(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    transfers_on: None,
    billing_on: None,
) -> None:
    from app.models import Payment, PaymentStatus
    from app.services import payments

    info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert info["transfer_accounts"] == [
        {"method": "whish", "account": "70 123 456"},
        {"method": "omt", "account": "Replisto SAL, 03 123 456"},
    ]
    body = {"amount_cents": 2500, "method": "whish", "reference": " WH-998877 "}
    resp = await client.post("/api/v1/billing/transfer", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["reference"] == "WH-998877"
    # The same receipt can't be sent twice, and the wallet waits for the team's check.
    resp = await client.post(
        "/api/v1/billing/transfer", json=body, headers={**auth_headers, **AR_HEADERS}
    )
    assert resp.status_code == 400 and resp.json()["detail"] == "سبق إرسال رقم التحويل هذا."
    info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert info["balance_cents"] == 0
    assert [t["amount_cents"] for t in info["pending_transfers"]] == [2500]

    payment = await db.scalar(select(Payment))
    assert payment is not None
    assert await payments.approve_transfer(db, payment)
    assert not await payments.approve_transfer(db, payment)  # credited once only
    info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert info["balance_cents"] == 2500 and info["pending_transfers"] == []

    # A transfer that never arrived is rejected and credits nothing.
    body = {"amount_cents": 1000, "method": "omt", "reference": "OMT-1"}
    await client.post("/api/v1/billing/transfer", json=body, headers=auth_headers)
    second = await db.scalar(select(Payment).where(Payment.gateway == "omt"))
    assert second is not None
    assert await payments.reject_transfer(db, second, "Not received")
    await db.refresh(second)
    assert second.status == PaymentStatus.FAILED
    info = (await client.get("/api/v1/billing", headers=auth_headers)).json()
    assert info["balance_cents"] == 2500


async def test_unoffered_transfer_method_is_refused(
    client: AsyncClient, auth_headers: dict, billing_on: None
) -> None:
    body = {"amount_cents": 2500, "method": "whish", "reference": "WH-1"}
    resp = await client.post("/api/v1/billing/transfer", json=body, headers=auth_headers)
    assert resp.status_code == 400 and "isn't available" in resp.json()["detail"]
