"""Inbox, unanswered questions, dashboard and account endpoints."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import encrypt_secret
from app.core.timeutil import utcnow
from app.models import Conversation, InstagramAccount, Message, MessageSender, Shop, User
from app.services.messaging import reply_to_conversation
from app.services.responder import PlaceholderResponder
from tests.conftest import FakeMeta


@pytest.fixture
async def inbox(
    client: AsyncClient, auth_headers: dict, sessions: async_sessionmaker[AsyncSession]
) -> dict:
    """Two conversations for the logged-in shop: one answered, one the bot couldn't answer."""
    async with sessions() as db:
        shop = await db.scalar(select(Shop))
        assert shop is not None
        now = utcnow()
        happy = Conversation(
            shop_id=shop.id,
            customer_id="111",
            customer_username="sara",
            last_customer_message_at=now - timedelta(minutes=5),
        )
        stuck = Conversation(
            shop_id=shop.id,
            customer_id="222",
            customer_username="",  # lookup failed
            last_customer_message_at=now,
        )
        db.add_all([happy, stuck])
        await db.flush()
        db.add_all(
            [
                Message(conversation_id=happy.id, sender=MessageSender.CUSTOMER, text="قیمت؟"),
                Message(conversation_id=happy.id, sender=MessageSender.BOT, text="۱۲۰ تومن"),
                Message(conversation_id=stuck.id, sender=MessageSender.CUSTOMER, text="سلام"),
                Message(
                    conversation_id=stuck.id, sender=MessageSender.CUSTOMER, text="فاکتور میدید؟"
                ),
                Message(
                    conversation_id=stuck.id,
                    sender=MessageSender.BOT,
                    text="همکارم جواب میده",
                    unanswered=True,
                ),
            ]
        )
        await db.commit()
        return {"happy": str(happy.id), "stuck": str(stuck.id)}


async def test_list_and_filter(client: AsyncClient, auth_headers: dict, inbox: dict) -> None:
    page = (await client.get("/api/v1/conversations", headers=auth_headers)).json()
    assert page["total"] == 2
    first, second = page["items"]
    assert first["id"] == inbox["stuck"]  # most recent first
    assert first["customer_username"] is None
    assert first["open_unanswered"] == 1
    assert second["last_message"]["text"] == "۱۲۰ تومن"

    only = await client.get(
        "/api/v1/conversations", headers=auth_headers, params={"filter": "unanswered"}
    )
    assert [c["id"] for c in only.json()["items"]] == [inbox["stuck"]]
    by_name = await client.get("/api/v1/conversations", headers=auth_headers, params={"q": "sar"})
    assert [c["id"] for c in by_name.json()["items"]] == [inbox["happy"]]


async def test_detail_pause_resume(client: AsyncClient, auth_headers: dict, inbox: dict) -> None:
    url = f"/api/v1/conversations/{inbox['happy']}"
    detail = (await client.get(url, headers=auth_headers)).json()
    assert [m["sender"] for m in detail["messages"]] == ["customer", "bot"]

    paused = (await client.post(f"{url}/pause", headers=auth_headers, json={"minutes": 30})).json()
    assert paused["bot_paused"] is True
    forever = (await client.post(f"{url}/pause", headers=auth_headers, json={})).json()
    assert forever["bot_paused"] is True

    listed = await client.get(
        "/api/v1/conversations", headers=auth_headers, params={"filter": "paused"}
    )
    assert [c["id"] for c in listed.json()["items"]] == [inbox["happy"]]

    resumed = (await client.post(f"{url}/resume", headers=auth_headers)).json()
    assert resumed["bot_paused"] is False and resumed["bot_paused_until"] is None


async def test_other_shop_cannot_see_conversation(client: AsyncClient, inbox: dict) -> None:
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "b@shop.ir", "password": "strongpass1", "shop_name": "B"},
    )
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get("/api/v1/conversations", headers=headers)).json()["total"] == 0
    resp = await client.get(f"/api/v1/conversations/{inbox['stuck']}", headers=headers)
    assert resp.status_code == 404


async def test_unanswered_list_and_resolve(
    client: AsyncClient, auth_headers: dict, inbox: dict
) -> None:
    [item] = (await client.get("/api/v1/unanswered", headers=auth_headers)).json()
    assert item["question"] == "سلام\nفاکتور میدید؟"
    assert item["conversation_id"] == inbox["stuck"]

    resp = await client.post(
        f"/api/v1/unanswered/{item['message_id']}/resolve", headers=auth_headers
    )
    assert resp.status_code == 204
    assert (await client.get("/api/v1/unanswered", headers=auth_headers)).json() == []


async def test_dashboard(client: AsyncClient, auth_headers: dict, inbox: dict) -> None:
    body = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()
    assert body["setup"] == {
        "instagram_available": True,
        "instagram_connected": False,
        "instagram_active": False,
        "instagram_username": None,
        "knowledge_entries": 0,
        "products_connected": False,
        "product_count": 0,
        "product_error": None,
        "ai_ready": False,
        "bot_enabled": False,
    }
    assert body["last_7_days"] == {
        "conversations": 2,
        "customer_messages": 3,
        "bot_replies": 2,
        "open_unanswered": 1,
    }


async def test_fallback_is_not_repeated(db: AsyncSession, fake_meta: FakeMeta) -> None:
    user = User(email="o@x.ir", password_hash="x")
    user.shop = Shop(name="s", bot_enabled=True, fallback_message="همکارم جواب میده")
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
    conversation = Conversation(shop_id=user.shop.id, customer_id="9")
    db.add(conversation)
    await db.flush()

    async def customer_says(text: str) -> None:
        now = utcnow()
        db.add(Message(conversation_id=conversation.id, sender=MessageSender.CUSTOMER, text=text))
        conversation.last_customer_message_at = now
        await db.commit()
        await reply_to_conversation(
            db, conversation.id, now, fake_meta.client(), PlaceholderResponder()
        )

    await customer_says("فاکتور میدید؟")
    await customer_says("؟؟")
    assert len(fake_meta.sent) == 1  # the second fallback is suppressed...
    flagged = await db.scalar(
        select(func.count()).select_from(Message).where(Message.unanswered.is_(True))
    )
    assert flagged == 2  # ...but the follow-up still lands in the owner's unanswered list


async def test_change_password_and_delete_account(
    client: AsyncClient, auth_headers: dict, inbox: dict, db: AsyncSession
) -> None:
    wrong = await client.post(
        "/api/v1/me/password",
        headers=auth_headers,
        json={"current_password": "nope", "new_password": "newpass123"},
    )
    assert wrong.status_code == 400
    ok = await client.post(
        "/api/v1/me/password",
        headers=auth_headers,
        json={"current_password": "strongpass1", "new_password": "newpass123"},
    )
    assert ok.status_code == 204
    login = await client.post(
        "/api/v1/auth/login", json={"email": "owner@shop.ir", "password": "newpass123"}
    )
    assert login.status_code == 200

    refused = await client.request(
        "DELETE", "/api/v1/me", headers=auth_headers, json={"password": "strongpass1"}
    )
    assert refused.status_code == 400
    deleted = await client.request(
        "DELETE", "/api/v1/me", headers=auth_headers, json={"password": "newpass123"}
    )
    assert deleted.status_code == 204
    for model in (User, Shop, Conversation, Message):
        assert await db.scalar(select(func.count()).select_from(model)) == 0
    assert (await client.get("/api/v1/me", headers=auth_headers)).status_code == 401
