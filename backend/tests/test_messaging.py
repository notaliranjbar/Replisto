import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import Conversation, InstagramAccount, Message, MessageSender, Shop, User
from app.services.instagram import InstagramError
from app.services.messaging import handle_event, reply_to_conversation
from app.services.responder import PlaceholderResponder, Reply
from app.services.webhook import MessagingEvent
from tests.conftest import FakeMeta, RecordingQueue

ACCOUNT = "17841400000000001"
CUSTOMER = "998877"


@pytest.fixture
async def shop(db: AsyncSession) -> Shop:
    user = User(email="owner@shop.com", password_hash="x")
    user.shop = Shop(
        name="Layla Boutique", bot_enabled=True, fallback_message="A teammate will reply soon"
    )
    db.add(user)
    await db.flush()
    db.add(
        InstagramAccount(
            shop_id=user.shop.id,
            ig_user_id=ACCOUNT,
            username="mahsa.boutique",
            access_token_encrypted=encrypt_secret("page-token"),
        )
    )
    await db.commit()
    return user.shop


def _event(
    mid: str, text: str = "Hi", *, echo: bool = False, at: datetime | None = None
) -> MessagingEvent:
    return MessagingEvent(
        account_ig_id=ACCOUNT,
        customer_igsid=CUSTOMER,
        mid=mid,
        text=text,
        is_echo=echo,
        timestamp=at or utcnow(),
    )


async def _receive(db: AsyncSession, queue: RecordingQueue, event: MessagingEvent) -> None:
    await handle_event(db, event, queue, debounce_seconds=5)


async def _run_reply_jobs(db: AsyncSession, queue: RecordingQueue, fake_meta: FakeMeta) -> None:
    """Run every queued reply job, like the worker would after the debounce delay."""
    jobs = [j for j in queue.jobs if j.function == "reply_conversation"]
    queue.jobs.clear()
    for job in jobs:
        conversation_id, trigger_at = job.args
        await reply_to_conversation(
            db,
            uuid.UUID(conversation_id),
            datetime.fromisoformat(trigger_at),
            fake_meta.client(),
            PlaceholderResponder(),
        )


async def _messages(db: AsyncSession) -> list[Message]:
    db.expire_all()
    return list((await db.scalars(select(Message).order_by(Message.created_at))).all())


async def test_customer_message_is_stored_and_answered(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    await _receive(db, queue, _event("m1", "Does this dress come in M?"))

    [job] = queue.jobs
    assert job.function == "reply_conversation"
    assert job.defer_seconds == 5

    await _run_reply_jobs(db, queue, fake_meta)

    [sent] = fake_meta.sent
    assert sent["recipient"] == {"id": CUSTOMER}
    assert sent["message"] == {"text": "A teammate will reply soon"}
    assert sent["token"] == "page-token"

    customer, bot = await _messages(db)
    assert customer.sender == MessageSender.CUSTOMER
    assert bot.sender == MessageSender.BOT
    assert bot.external_id == "bot-mid-1"
    assert bot.unanswered is True


async def test_webhook_retry_is_ignored(
    db: AsyncSession, shop: Shop, queue: RecordingQueue
) -> None:
    event = _event("m1")
    await _receive(db, queue, event)
    await _receive(db, queue, event)
    assert len(queue.jobs) == 1
    assert len(await _messages(db)) == 1


async def test_burst_of_messages_gets_one_reply(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    now = utcnow()
    await _receive(db, queue, _event("m1", "Hi", at=now))
    await _receive(db, queue, _event("m2", "this dress", at=now + timedelta(seconds=1)))
    await _receive(db, queue, _event("m3", "Do you have M?", at=now + timedelta(seconds=2)))
    assert len(queue.jobs) == 3

    await _run_reply_jobs(db, queue, fake_meta)
    assert len(fake_meta.sent) == 1


async def test_disabled_bot_stays_silent(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    shop.bot_enabled = False
    await db.commit()
    await _receive(db, queue, _event("m1"))
    await _run_reply_jobs(db, queue, fake_meta)
    assert fake_meta.sent == []


async def test_owner_reply_pauses_bot(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    now = utcnow()
    await _receive(db, queue, _event("m1", "Price?", at=now))
    # The owner answers by hand before the debounce delay is over.
    await _receive(db, queue, _event("o1", "It's 120, dear", echo=True))
    await _run_reply_jobs(db, queue, fake_meta)
    assert fake_meta.sent == []

    conversation = await db.scalar(select(Conversation))
    assert conversation is not None and conversation.bot_paused_until is not None
    assert as_utc(conversation.bot_paused_until) > utcnow() + timedelta(minutes=100)

    # While paused, new customer messages are recorded but not answered.
    await _receive(db, queue, _event("m2", "Thanks", at=now + timedelta(seconds=10)))
    await _run_reply_jobs(db, queue, fake_meta)
    assert fake_meta.sent == []
    senders = [m.sender for m in await _messages(db)]
    assert senders == [MessageSender.CUSTOMER, MessageSender.OWNER, MessageSender.CUSTOMER]


async def test_echo_of_bot_reply_does_not_pause_bot(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    await _receive(db, queue, _event("m1"))
    await _run_reply_jobs(db, queue, fake_meta)
    # Meta echoes our own message back with the mid the send call returned.
    await _receive(db, queue, _event("bot-mid-1", "A teammate will reply soon", echo=True))

    conversation = await db.scalar(select(Conversation))
    assert conversation is not None and conversation.bot_paused_until is None
    assert [m.sender for m in await _messages(db)] == [MessageSender.CUSTOMER, MessageSender.BOT]


async def test_echo_racing_the_send_is_matched_to_bot_message(
    db: AsyncSession, shop: Shop, queue: RecordingQueue
) -> None:
    await _receive(db, queue, _event("m1"))
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None
    # A bot message saved just before sending, whose send call hasn't returned yet.
    db.add(Message(conversation_id=conversation.id, sender=MessageSender.BOT, text="Sending"))
    await db.commit()

    await _receive(db, queue, _event("bot-mid-9", "Sending", echo=True))

    await db.refresh(conversation)
    assert conversation.bot_paused_until is None
    bot = await db.scalar(select(Message).where(Message.sender == MessageSender.BOT))
    assert bot is not None and bot.external_id == "bot-mid-9"


async def test_unknown_account_is_ignored(db: AsyncSession, queue: RecordingQueue) -> None:
    await _receive(db, queue, _event("m1"))
    assert queue.jobs == []
    assert await _messages(db) == []


async def test_no_reply_outside_24h_window(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    await _receive(db, queue, _event("m1", at=utcnow() - timedelta(hours=25)))
    await _run_reply_jobs(db, queue, fake_meta)
    assert fake_meta.sent == []


async def test_revoked_token_deactivates_account(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    fake_meta.send_error = (400, {"error": {"message": "Session expired", "code": 190}})
    await _receive(db, queue, _event("m1"))
    await _run_reply_jobs(db, queue, fake_meta)

    account = await db.scalar(select(InstagramAccount))
    assert account is not None and account.is_active is False
    # The failed bot message is not left behind as if it had been sent.
    assert [m.sender for m in await _messages(db)] == [MessageSender.CUSTOMER]


async def test_rate_limit_error_is_raised_for_retry(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    fake_meta.send_error = (400, {"error": {"message": "Too many calls", "code": 4}})
    await _receive(db, queue, _event("m1"))
    with pytest.raises(InstagramError) as exc_info:
        await _run_reply_jobs(db, queue, fake_meta)
    assert exc_info.value.retryable

    # The retry succeeds once Meta recovers.
    fake_meta.send_error = None
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None
    await reply_to_conversation(
        db,
        conversation.id,
        as_utc(conversation.last_customer_message_at),
        fake_meta.client(),
        PlaceholderResponder(),
    )
    assert len(fake_meta.sent) == 1


async def test_long_reply_is_split_into_chunks(
    db: AsyncSession, shop: Shop, queue: RecordingQueue, fake_meta: FakeMeta
) -> None:
    class LongResponder:
        async def generate(self, shop: Shop, history: list[Message], **_: object) -> Reply:
            return Reply(text=("A sentence about the product. " * 120).strip())

    await _receive(db, queue, _event("m1"))
    conversation = await db.scalar(select(Conversation))
    assert conversation is not None
    await reply_to_conversation(
        db,
        conversation.id,
        as_utc(conversation.last_customer_message_at),
        fake_meta.client(),
        LongResponder(),
    )
    assert len(fake_meta.sent) >= 2
    bots = [m for m in await _messages(db) if m.sender == MessageSender.BOT]
    assert len(bots) == len(fake_meta.sent)
    assert all(m.external_id for m in bots)
