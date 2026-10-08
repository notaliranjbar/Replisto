"""Handoffs: DMs the bot couldn't answer, waiting for the shop owner in the panel."""

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import encrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import (
    Conversation,
    HandoffResolution,
    InstagramAccount,
    Message,
    MessageSender,
    Shop,
)
from app.services.messaging import handle_event, reply_to_conversation
from app.services.responder import ChatTurn, PlaceholderResponder, Reply
from app.services.webhook import MessagingEvent
from tests.conftest import FakeMeta, RecordingQueue

ACCOUNT = "17841400000000001"
CUSTOMER = "998877"


class ScriptedResponder:
    """Answers when it "knows" the question, otherwise hands off with a reason."""

    def __init__(self, known: dict[str, str]) -> None:
        self.known = known

    async def generate(self, shop: Shop, history: list[ChatTurn], **_: object) -> Reply:
        last = history[-1].text
        if last in self.known:
            return Reply(text=self.known[last])
        return Reply(
            text=shop.fallback_message,
            unanswered=True,
            handoff_reason="A question outside the shop information",
        )


@pytest.fixture
async def shop(client: AsyncClient, auth_headers: dict, sessions: async_sessionmaker) -> Shop:
    """The logged-in user's shop, connected to Instagram with the bot on."""
    async with sessions() as db:
        shop = await db.scalar(select(Shop))
        assert shop is not None
        shop.bot_enabled = True
        shop.fallback_message = "A teammate will reply soon"
        shop.handoff_pause_minutes = 0  # keep the bot active after owner replies, to test that
        db.add(
            InstagramAccount(
                shop_id=shop.id,
                ig_user_id=ACCOUNT,
                username="mahsa",
                access_token_encrypted=encrypt_secret("t"),
            )
        )
        await db.commit()
        return shop


async def _customer(
    db: AsyncSession, queue: RecordingQueue, fake_meta: FakeMeta, text: str, responder
) -> None:
    """A customer message arrives and the debounced reply job runs."""
    event = MessagingEvent(
        account_ig_id=ACCOUNT,
        customer_igsid=CUSTOMER,
        mid=f"m-{uuid.uuid4().hex}",
        text=text,
        is_echo=False,
        timestamp=utcnow(),
    )
    await handle_event(db, event, queue, debounce_seconds=0)
    for job in [j for j in queue.jobs if j.function == "reply_conversation"]:
        await reply_to_conversation(
            db,
            uuid.UUID(job.args[0]),
            datetime.fromisoformat(job.args[1]),
            fake_meta.client(),
            responder,
        )
    queue.jobs.clear()
    db.expire_all()


async def _owner_replies(db: AsyncSession, queue: RecordingQueue, text: str) -> None:
    event = MessagingEvent(
        account_ig_id=ACCOUNT,
        customer_igsid=CUSTOMER,
        mid=f"o-{uuid.uuid4().hex}",
        text=text,
        is_echo=True,
        timestamp=utcnow(),
    )
    await handle_event(db, event, queue, debounce_seconds=0)
    db.expire_all()


async def _conversation(db: AsyncSession) -> Conversation:
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None
    return conversation


async def test_full_handoff_lifecycle(
    client: AsyncClient,
    auth_headers: dict,
    shop: Shop,
    db: AsyncSession,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
) -> None:
    bot = ScriptedResponder({"How's shipping?": "By express post"})

    # 1. A question the bot knows: no handoff.
    await _customer(db, queue, fake_meta, "How's shipping?", bot)
    assert (await _conversation(db)).handoff_at is None

    # 2. One it doesn't: the customer gets the fallback once, the owner gets a handoff.
    await _customer(db, queue, fake_meta, "Do you issue formal invoices?", bot)
    conversation = await _conversation(db)
    assert conversation.handoff_open
    assert conversation.handoff_reason == "A question outside the shop information"
    assert conversation.handoff_question == "Do you issue formal invoices?"
    assert [m["message"]["text"] for m in fake_meta.sent] == [
        "By express post",
        "A teammate will reply soon",
    ]

    # 3. While waiting, the customer writes again: no second fallback, question grows,
    #    and a known question still gets answered.
    await _customer(db, queue, fake_meta, "Do you need our VAT number?", bot)
    await _customer(db, queue, fake_meta, "How's shipping?", bot)
    assert [m["message"]["text"] for m in fake_meta.sent][2:] == ["By express post"]
    conversation = await _conversation(db)
    assert (
        conversation.handoff_question
        == "Do you issue formal invoices?\nDo you need our VAT number?"
    )

    # The panel shows it.
    page = (await client.get("/api/v1/handoffs", headers=auth_headers)).json()
    assert page["total"] == 1
    [item] = page["items"]
    assert item["handoff"]["status"] == "open"
    assert (
        item["handoff"]["question"] == "Do you issue formal invoices?\nDo you need our VAT number?"
    )
    dashboard = (await client.get("/api/v1/dashboard", headers=auth_headers)).json()
    assert dashboard["open_handoffs"] == 1
    needs_owner = await client.get(
        "/api/v1/conversations", headers=auth_headers, params={"filter": "needs_owner"}
    )
    assert needs_owner.json()["total"] == 1

    # 4. The owner answers on Instagram: the handoff closes by itself.
    await _owner_replies(db, queue, "Yes, we issue formal invoices")
    conversation = await _conversation(db)
    assert not conversation.handoff_open
    assert conversation.handoff_resolved_by == HandoffResolution.OWNER_REPLY
    assert (await client.get("/api/v1/handoffs", headers=auth_headers)).json()["total"] == 0
    resolved = await client.get(
        "/api/v1/handoffs", headers=auth_headers, params={"status": "resolved"}
    )
    assert resolved.json()["items"][0]["handoff"]["resolved_by"] == "owner_reply"

    # 5. A later unknown question starts a new handoff and gets the fallback again.
    sent_before = len(fake_meta.sent)
    await _customer(db, queue, fake_meta, "Do you have a physical store?", bot)
    assert len(fake_meta.sent) == sent_before + 1
    conversation = await _conversation(db)
    assert conversation.handoff_open
    assert conversation.handoff_question == "Do you have a physical store?"


async def test_resolve_from_panel(
    client: AsyncClient,
    auth_headers: dict,
    shop: Shop,
    db: AsyncSession,
    queue: RecordingQueue,
    fake_meta: FakeMeta,
) -> None:
    await _customer(db, queue, fake_meta, "A hard question", PlaceholderResponder())
    conversation = await _conversation(db)
    url = f"/api/v1/handoffs/{conversation.id}/resolve"
    assert (await client.post(url, headers=auth_headers)).status_code == 204
    assert (await client.post(url, headers=auth_headers)).status_code == 204  # idempotent

    db.expire_all()
    conversation = await _conversation(db)
    assert conversation.handoff_resolved_by == HandoffResolution.MANUAL
    detail = (
        await client.get(f"/api/v1/conversations/{conversation.id}", headers=auth_headers)
    ).json()
    assert detail["handoff"]["status"] == "resolved"


async def test_failed_send_is_retried_before_handing_off(
    shop: Shop, db: AsyncSession, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    """A temporary Instagram error must not leave the customer without any reply."""
    from app.services.instagram import InstagramError

    fake_meta.send_error = (400, {"error": {"message": "rate limited", "code": 4}})
    with pytest.raises(InstagramError):
        await _customer(db, queue, fake_meta, "A hard question", PlaceholderResponder())
    assert not (await _conversation(db)).handoff_open

    fake_meta.send_error = None
    conversation = await _conversation(db)
    await reply_to_conversation(
        db,
        conversation.id,
        as_utc(conversation.last_customer_message_at),
        fake_meta.client(),
        PlaceholderResponder(),
    )
    assert [m["message"]["text"] for m in fake_meta.sent] == ["A teammate will reply soon"]
    db.expire_all()
    assert (await _conversation(db)).handoff_open


async def test_handoff_is_private_to_shop(client: AsyncClient, shop: Shop, db, queue, fake_meta):
    await _customer(db, queue, fake_meta, "Question", PlaceholderResponder())
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "b@shop.com", "password": "strongpass1", "shop_name": "B"},
    )
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get("/api/v1/handoffs", headers=headers)).json()["total"] == 0
    conversation = await _conversation(db)
    resp = await client.post(f"/api/v1/handoffs/{conversation.id}/resolve", headers=headers)
    assert resp.status_code == 404


async def test_bot_messages_are_flagged(shop: Shop, db: AsyncSession, queue, fake_meta) -> None:
    await _customer(db, queue, fake_meta, "Question", PlaceholderResponder())
    bot = await db.scalar(select(Message).where(Message.sender == MessageSender.BOT))
    assert bot is not None and bot.unanswered


async def test_api_times_carry_timezone(
    client: AsyncClient, auth_headers: dict, shop: Shop, db: AsyncSession, queue, fake_meta
) -> None:
    """Without an offset the browser would read UTC times as local time."""
    await _customer(db, queue, fake_meta, "Question", PlaceholderResponder())
    [item] = (await client.get("/api/v1/handoffs", headers=auth_headers)).json()["items"]
    for value in (item["last_customer_message_at"], item["handoff"]["handed_off_at"]):
        assert value.endswith(("Z", "+00:00")), value


async def test_partial_answer_while_waiting_sends_only_the_known_part(
    shop: Shop, db: AsyncSession, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    class Partial:
        async def generate(self, shop: Shop, history: list[ChatTurn], **_: object) -> Reply:
            return Reply(
                text=f"Size exchanges within 7 days.\n{shop.fallback_message}",
                unanswered=True,
                handoff_reason="Refunds aren't in the shop information",
                partial_answer="Size exchanges within 7 days.",
            )

    await _customer(db, queue, fake_meta, "Do you issue formal invoices?", PlaceholderResponder())
    await _customer(db, queue, fake_meta, "Can I return things?", Partial())
    # First: the fallback. Second (handoff already open): only the part it knew, no repeat.
    assert [m["message"]["text"] for m in fake_meta.sent] == [
        "A teammate will reply soon",
        "Size exchanges within 7 days.",
    ]
    conversation = await _conversation(db)
    assert conversation.handoff_open
    assert conversation.handoff_question == "Do you issue formal invoices?\nCan I return things?"


async def test_retried_partial_answer_records_question_once(
    shop: Shop, db: AsyncSession, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    from app.services.instagram import InstagramError

    class Partial:
        async def generate(self, shop: Shop, history: list[ChatTurn], **_: object) -> Reply:
            return Reply(
                text="x",
                unanswered=True,
                handoff_reason="r",
                partial_answer="Exchanges are possible.",
            )

    await _customer(db, queue, fake_meta, "Invoice?", PlaceholderResponder())
    fake_meta.send_error = (400, {"error": {"message": "rate limited", "code": 4}})
    with pytest.raises(InstagramError):
        await _customer(db, queue, fake_meta, "Returns?", Partial())
    fake_meta.send_error = None
    conversation = await _conversation(db)
    await reply_to_conversation(
        db,
        conversation.id,
        as_utc(conversation.last_customer_message_at),
        fake_meta.client(),
        Partial(),
    )
    db.expire_all()
    assert (await _conversation(db)).handoff_question == "Invoice?\nReturns?"
    assert [m["message"]["text"] for m in fake_meta.sent] == [
        "A teammate will reply soon",
        "Exchanges are possible.",
    ]
