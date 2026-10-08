"""Replisto's own assistant on the website, and owner alerts by email."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Channel,
    Conversation,
    KnowledgeEntry,
    KnowledgeSection,
    Shop,
    User,
)
from app.services import notify
from tests.conftest import FakeWeb

VISITOR = str(uuid.uuid4())


@pytest.fixture
async def team(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    """The team's account, owning Replisto's own shop."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "team@replisto.app", "password": "strongpass1", "shop_name": "Replisto"},
    )
    shop = await db.scalar(select(Shop).join(User).where(User.email == "team@replisto.app"))
    assert shop is not None
    shop.is_house = True
    shop.bot_enabled = True
    db.add(
        KnowledgeEntry(
            shop_id=shop.id, section=KnowledgeSection.ABOUT, content="Replisto answers shops' DMs"
        )
    )
    await db.commit()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _fresh_site_limits() -> None:
    from app.api.routes import site

    site._per_visitor.clear()
    site._per_ip.clear()


async def _chat(client: AsyncClient, text: str, headers: dict | None = None):  # type: ignore[no-untyped-def]
    return await client.post(
        "/api/v1/site/chat", json={"visitor": VISITOR, "text": text}, headers=headers or {}
    )


async def _state(client: AsyncClient, visitor: str = VISITOR) -> dict:
    return (await client.get("/api/v1/site/chat", params={"visitor": visitor})).json()


async def test_not_set_up(client: AsyncClient) -> None:
    assert (await _state(client))["available"] is False
    assert (await _chat(client, "Hi")).status_code == 503


async def test_a_guest_asks_about_replisto(
    client: AsyncClient, team: dict, fake_web: FakeWeb, llm_on: None, billing_on: None
) -> None:
    body = await _state(client)
    assert body["available"] and body["messages"] == []
    assert body["quota"]["tier"] == "guest" and body["quota"]["left_percent"] == 100

    fake_web.llm_replies = [{"content": "Replisto answers your customers' messages"}]
    resp = await _chat(client, "What does Replisto do?")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["sender"] for m in body["messages"]] == ["customer", "bot"]
    assert body["quota"]["used_tokens"] == 120
    # It knows our live prices and isn't charged to any wallet.
    system = fake_web.llm_requests[-1]["messages"][0]["content"]
    assert "CURRENT PRICES OF REPLISTO" in system and "website chat" in system
    billing = (await client.get("/api/v1/billing", headers=team)).json()
    assert billing["balance_cents"] == 0
    # The chat shows up in the team's inbox like any conversation.
    inbox = (await client.get("/api/v1/conversations", headers=team)).json()
    assert inbox["items"][0]["channel"] == "web"


async def test_the_daily_allowance(
    client: AsyncClient,
    team: dict,
    fake_web: FakeWeb,
    llm_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "site_chat_guest_tokens", 150)
    assert (await _chat(client, "Hi")).status_code == 200  # 120 tokens of 150
    body = await _state(client)
    assert body["quota"]["left_percent"] == 20 and body["quota"]["answers_left"] == 0
    assert (await _chat(client, "How much does it cost?")).status_code == 200
    resp = await _chat(client, "And what about Arabic?")
    assert resp.status_code == 429 and "account" in resp.json()["detail"]
    body = await _state(client)
    assert body["quota"]["exhausted"] == "personal" and body["quota"]["left_percent"] == 0

    # Another browser on the same network: blocked once the network's allowance is used.
    monkeypatch.setattr(get_settings(), "site_chat_ip_tokens", 240)
    other = str(uuid.uuid4())
    resp = await client.post("/api/v1/site/chat", json={"visitor": other, "text": "Hi"})
    assert resp.status_code == 429
    assert (await _state(client, other))["quota"]["exhausted"] == "network"

    # Logging in gives the bigger, personal member allowance.
    member = await client.post(
        "/api/v1/auth/register",
        json={"email": "shop@owner.com", "password": "strongpass1", "shop_name": "S"},
    )
    headers = {"Authorization": f"Bearer {member.json()['access_token']}"}
    resp = await _chat(client, "Hi", headers)
    assert resp.status_code == 200 and resp.json()["quota"]["tier"] == "member"


async def test_the_team_answers_what_the_bot_cannot(
    client: AsyncClient,
    team: dict,
    fake_web: FakeWeb,
    llm_on: None,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mails: list[tuple[str, str, str]] = []

    async def fake_send(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        mails.append((to, subject, body))

    monkeypatch.setattr(notify, "send_email", fake_send)
    fake_web.llm_replies = [
        FakeWeb.tool_call(
            "handoff_to_human",
            {"reason": "Agency deal", "message": "I've passed your question to the team"},
        )
    ]
    body = (await _chat(client, "Do you have a plan for agencies with 20 shops?")).json()
    assert body["waiting_for_team"] is True
    # The team hears about it by email, with the question.
    [(to, subject, text)] = mails
    assert to == "team@replisto.app" and subject == "A customer is waiting for you"
    assert "20 shops" in text and "/inbox/" in text

    conversation = await db.scalar(select(Conversation).where(Conversation.channel == Channel.WEB))
    assert conversation is not None
    resp = await client.post(
        f"/api/v1/conversations/{conversation.id}/reply",
        json={"text": "Yes, let's talk!"},
        headers=team,
    )
    assert resp.status_code == 200, resp.text
    body = await _state(client)
    assert body["messages"][-1]["sender"] == "owner"
    assert body["messages"][-1]["text"] == "Yes, let's talk!"
    assert body["waiting_for_team"] is False


async def test_bad_input(client: AsyncClient, team: dict) -> None:
    resp = await client.post("/api/v1/site/chat", json={"visitor": "x" * 36, "text": "Hi"})
    assert resp.status_code == 400
    assert (await _chat(client, "a" * 601)).status_code == 422
