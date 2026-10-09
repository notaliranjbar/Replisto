"""The message pipeline: record incoming customer messages, then reply after a short debounce.

    channel webhook ──► record_customer_message ──(enqueue, delayed)──► reply_to_conversation
                                                                              │
                                         ChannelSender (Instagram) ◄────┘

Decisions that are easy to get wrong live here:
- Channels retry webhooks, so everything is idempotent on the message's external id.
- Customers send bursts of short messages; each schedules a reply, but only the job for the
  newest message actually answers.
- When the owner answers by hand the bot steps back for `shop.handoff_pause_minutes`. On
  Instagram our own sends come back as echoes and must not be mistaken for the owner.
- When the bot can't answer, the conversation is handed off: the customer gets a message
  once, the question waits in the owner's panel, and the owner is alerted there.
- Every AI answer is paid from the shop's wallet, once, after it is delivered. With an empty
  wallet the bot doesn't call the AI: the customer gets the fallback message and the
  conversation goes to the owner.
"""

import dataclasses
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.queue import Queue
from app.core.security import decrypt_secret
from app.core.timeutil import as_utc, utcnow
from app.models import (
    Channel,
    Conversation,
    HandoffResolution,
    InstagramAccount,
    Message,
    MessageSender,
    ScheduledStory,
    Shop,
)
from app.services import billing
from app.services.channels import ChannelSender, Gateways, SendError, sender_for, split_text
from app.services.instagram import InstagramClient, InstagramError
from app.services.llm import LLMError
from app.services.notify import Notifier, NullNotifier
from app.services.posts import POST_MARKER, PostLink, post_key
from app.services.responder import ChatTurn, Responder, looks_on_topic
from app.services.webhook import MessagingEvent

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20
CHANNEL_NAMES = {Channel.INSTAGRAM: "Instagram", Channel.WEB: "the website"}
EMPTY_WALLET_REASON = "The Replisto wallet is empty"


# ---------------------------------------------------------------------------- incoming


async def handle_event(
    db: AsyncSession,
    event: MessagingEvent,
    queue: Queue,
    *,
    debounce_seconds: float,
    instagram: InstagramClient | None = None,
) -> None:
    """An Instagram webhook message event."""
    if not get_settings().instagram_enabled:
        return
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.ig_user_id == event.account_ig_id,
            InstagramAccount.is_active.is_(True),
        )
    )
    if account is None:
        logger.info("webhook for unknown or inactive account %s", event.account_ig_id)
        return
    if await message_exists(db, event.mid):
        return

    shop = await db.get(Shop, account.shop_id)
    assert shop is not None  # FK guarantees it
    conversation = await get_or_create_conversation(
        db, shop.id, Channel.INSTAGRAM, "", event.customer_igsid
    )

    if event.is_echo:
        await _record_echo(db, shop, conversation, event)
        return
    if conversation.customer_username is None and instagram is not None:
        await _lookup_username(db, conversation, account, instagram)

    text = event.display_text
    if event.story_id:
        text = await _with_story_note(db, shop.id, event.story_id, text)
    await record_customer_message(
        db,
        conversation,
        external_id=event.mid,
        text=text,
        at=event.timestamp,
        queue=queue,
        debounce_seconds=debounce_seconds,
    )


async def record_customer_message(
    db: AsyncSession,
    conversation: Conversation,
    *,
    external_id: str,
    text: str,
    at: datetime,
    queue: Queue,
    debounce_seconds: float,
) -> bool:
    """Store a customer message and schedule the reply. False if it was a duplicate."""
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.CUSTOMER,
            text=text,
            external_id=external_id,
        )
    )
    last = conversation.last_customer_message_at
    if last is None or at > as_utc(last):
        conversation.last_customer_message_at = at
    if not await _commit_ignoring_duplicate(db):
        return False
    await queue.enqueue(
        "reply_conversation",
        str(conversation.id),
        at.isoformat(),
        job_id=f"reply:{external_id}",
        defer_seconds=debounce_seconds,
    )
    return True


async def record_owner_message(
    db: AsyncSession,
    shop: Shop,
    conversation: Conversation,
    *,
    text: str,
    external_id: str | None,
) -> None:
    """The owner answered the customer by hand: the bot steps back and the handoff closes."""
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.OWNER,
            text=text,
            external_id=external_id,
        )
    )
    if shop.handoff_pause_minutes > 0:
        conversation.bot_paused_until = utcnow() + timedelta(minutes=shop.handoff_pause_minutes)
    if conversation.handoff_open:
        conversation.handoff_resolved_at = utcnow()
        conversation.handoff_resolved_by = HandoffResolution.OWNER_REPLY
    await _commit_ignoring_duplicate(db)


async def _record_echo(
    db: AsyncSession, shop: Shop, conversation: Conversation, event: MessagingEvent
) -> None:
    # Our own reply whose echo arrived before the send call returned its mid: we store each
    # bot message *before* sending it, so match the in-flight one by text.
    pending = await db.scalars(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.sender == MessageSender.BOT,
            Message.external_id.is_(None),
        )
    )
    for message in pending:
        if _is_our_echo(message.text, event):
            message.external_id = event.mid
            await _commit_ignoring_duplicate(db)
            return
    await record_owner_message(
        db, shop, conversation, text=event.display_text, external_id=event.mid
    )


# ---------------------------------------------------------------------------- replying


async def reply_to_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    trigger_at: datetime,
    instagram: InstagramClient | None,
    responder: Responder,
    *,
    notifier: Notifier | None = None,
) -> None:
    """Answer the conversation, unless something newer or someone else already took over.

    Raises the channel's error (InstagramError) or LLMError when the failure
    is retryable, so the worker can retry the job.
    """
    notifier = notifier or NullNotifier()
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.last_customer_message_at is None:
        return
    last_customer_at = as_utc(conversation.last_customer_message_at)
    if last_customer_at > trigger_at:
        return  # a newer message arrived; its own job will answer everything at once

    shop = await db.get(Shop, conversation.shop_id)
    if shop is None or not shop.bot_enabled:
        return
    sender = await sender_for(db, shop, conversation, Gateways(instagram=instagram))
    if sender is None:
        return
    now = utcnow()
    if conversation.bot_paused_until and as_utc(conversation.bot_paused_until) > now:
        return
    if sender.reply_window is not None and now - last_customer_at > sender.reply_window:
        logger.info("conversation %s is outside the reply window", conversation.id)
        return

    history = list(
        reversed(
            (
                await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(HISTORY_LIMIT)
                )
            ).all()
        )
    )
    if not history or history[-1].sender != MessageSender.CUSTOMER:
        return  # already answered, by us or by the owner
    if await _too_many_replies(db, conversation):
        logger.warning("conversation %s hit the hourly reply limit", conversation.id)
        return
    if not billing.can_spend(shop):
        await _answer_with_empty_wallet(db, shop, conversation, history, sender, notifier)
        return

    streak = _off_topic_streak(history)
    if streak >= get_settings().off_topic_max_replies > 0 and not looks_on_topic(
        _latest_customer_text(history), []
    ):
        # Already told twice that the bot only helps with the shop: stay quiet, no AI call,
        # until the customer asks something that looks like a shopping question.
        logger.info("conversation %s: off-topic again, staying quiet", conversation.id)
        return

    await sender.typing()
    turns = [ChatTurn(sender=m.sender.value, text=m.text) for m in history]
    try:
        reply = await responder.generate(shop, turns, channel=conversation.channel)
    except LLMError as exc:
        if exc.retryable:
            raise
        logger.error("LLM rejected request for shop %s: %s", shop.id, exc)
        return
    if reply is None or not reply.text.strip():
        return
    tokens = (reply.prompt_tokens, reply.completion_tokens)
    if reply.off_topic:
        if streak >= get_settings().off_topic_max_replies:
            return
        # The canned "I only help with the shop": not charged, no handoff.
        await _send_text(db, conversation, sender, reply.text, False, tokens, off_topic=True)
        await db.commit()
        return
    if reply.unanswered and conversation.handoff_open:
        # The customer already got the "a colleague will answer" message; repeating it on
        # every follow-up is noise. Only the part the bot could answer (if any) is sent; the
        # question joins the open handoff below, once, after sending.
        history[-1].unanswered = True
        if not reply.partial_answer:
            await _open_handoff(db, shop, conversation, history, reply.handoff_reason, notifier)
            await _charge(db, shop, conversation, tokens, notifier)
            return
        reply = dataclasses.replace(reply, text=reply.partial_answer)

    delivered = await _send_text(db, conversation, sender, reply.text, reply.unanswered, tokens)
    if delivered and reply.posts:
        await _send_posts(db, conversation, sender, reply.posts)

    if reply.unanswered:
        # Opens a handoff, or adds to the open one. Runs only after sending (a retryable
        # failure raised above), so a retried job records the question exactly once. Even if
        # the message couldn't be delivered, the owner must see the question.
        await _open_handoff(db, shop, conversation, history, reply.handoff_reason, notifier)
    await db.commit()
    await _charge(db, shop, conversation, tokens, notifier)


async def _send_text(
    db: AsyncSession,
    conversation: Conversation,
    sender: ChannelSender,
    text: str,
    unanswered: bool,
    tokens: tuple[int | None, int | None] = (None, None),
    *,
    off_topic: bool = False,
) -> bool:
    """Send `text` in chunks, storing each bot message first. False if it couldn't be
    delivered; raises the channel's error when it is worth retrying."""
    for index, chunk in enumerate(split_text(text, sender.max_text_length)):
        message = Message(
            conversation_id=conversation.id,
            sender=MessageSender.BOT,
            text=chunk,
            unanswered=unanswered,
            off_topic=off_topic,
            prompt_tokens=tokens[0] if index == 0 else None,
            completion_tokens=tokens[1] if index == 0 else None,
        )
        db.add(message)
        await db.commit()
        try:
            external_id = await sender.send_text(chunk)
        except SendError as exc:
            await db.delete(message)
            await db.commit()
            if exc.retryable:
                # Nothing is recorded as handed off or charged yet, so the retry starts clean.
                raise exc.original from exc
            if not exc.endpoint_dead:
                logger.warning("send failed for conversation %s: %s", conversation.id, exc)
            return False
        message.external_id = external_id
        await db.commit()
    return True


async def _answer_with_empty_wallet(
    db: AsyncSession,
    shop: Shop,
    conversation: Conversation,
    history: list[Message],
    sender: ChannelSender,
    notifier: Notifier,
) -> None:
    """No credit left: no AI call. The customer hears from a person instead."""
    history[-1].unanswered = True
    if not conversation.handoff_open:
        await _send_text(db, conversation, sender, shop.fallback_message, unanswered=True)
    await _open_handoff(db, shop, conversation, history, EMPTY_WALLET_REASON, notifier)
    await db.commit()
    if await billing.should_remind_empty(db, shop):
        await _safe_notify(notifier.wallet_empty(shop))


async def _charge(
    db: AsyncSession,
    shop: Shop,
    conversation: Conversation,
    tokens: tuple[int | None, int | None],
    notifier: Notifier,
) -> None:
    running_low = await billing.charge_usage(
        db,
        shop,
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        description=f"Customer reply on {CHANNEL_NAMES.get(conversation.channel, 'Instagram')}",
        details={"conversation_id": str(conversation.id)},
    )
    if running_low:
        await _safe_notify(notifier.wallet_low(shop))


def _off_topic_streak(history: list[Message]) -> int:
    """How many off-topic redirects the bot sent in a row (since the last real answer)."""
    streak = 0
    for message in reversed(history):
        if message.sender == MessageSender.CUSTOMER:
            continue
        if message.sender == MessageSender.BOT and message.off_topic:
            streak += 1
            continue
        break
    return streak


def _latest_customer_text(history: list[Message]) -> str:
    parts: list[str] = []
    for message in reversed(history):
        if message.sender != MessageSender.CUSTOMER:
            break
        parts.insert(0, message.text)
    return "\n".join(parts)


async def _too_many_replies(db: AsyncSession, conversation: Conversation) -> bool:
    limit = get_settings().max_bot_replies_per_customer_hour
    if limit <= 0:
        return False
    recent = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.sender == MessageSender.BOT,
            Message.created_at >= utcnow() - timedelta(hours=1),
        )
    )
    return (recent or 0) >= limit


async def _open_handoff(
    db: AsyncSession,
    shop: Shop,
    conversation: Conversation,
    history: list[Message],
    reason: str | None,
    notifier: Notifier,
) -> None:
    """Start a handoff (and alert the owner), or add the latest question to the open one."""
    asked: list[str] = []
    for message in reversed(history):
        if message.sender != MessageSender.CUSTOMER:
            break
        asked.insert(0, message.text)
    question = "\n".join(asked)
    if conversation.handoff_open:
        conversation.handoff_question = "\n".join(
            filter(None, [conversation.handoff_question, question])
        )
        await db.commit()
        return
    conversation.handoff_at = utcnow()
    conversation.handoff_reason = (reason or "")[:255] or None
    conversation.handoff_question = question
    conversation.handoff_resolved_at = None
    conversation.handoff_resolved_by = None
    await db.commit()
    await _safe_notify(notifier.handoff(shop, conversation))


async def _safe_notify(call) -> None:  # type: ignore[no-untyped-def]
    """Alerts are best effort: a failed alert must never fail or retry a customer reply."""
    try:
        await call
    except Exception:
        logger.exception("owner notification failed")


# Echo attachment types that can't be a post we shared (the owner sending media by hand).
_OWNER_MEDIA = {"image", "video", "audio", "file", "sticker", "animated_image"}


def _is_our_echo(stored_text: str, event: MessagingEvent) -> bool:
    """Does this echo belong to a bot message we stored before sending it?"""
    if stored_text == event.text:
        return True
    if not stored_text.startswith(POST_MARKER):
        return False
    if event.text:  # a post sent as a plain link (no media id)
        return post_key(event.text) == post_key(stored_text)
    # A shared post echoes back as an attachment without text.
    return bool(event.attachment_types) and not set(event.attachment_types) & _OWNER_MEDIA


async def _send_posts(
    db: AsyncSession, conversation: Conversation, sender: ChannelSender, posts: list[PostLink]
) -> None:
    """Send each product post after the reply (a native post card, a copied channel post, a
    photo or a link, depending on the channel).

    Posts are an extra: a failure is logged and never fails or retries the reply itself,
    which the customer already has.
    """
    for post in posts:
        message = Message(
            conversation_id=conversation.id,
            sender=MessageSender.BOT,
            text=f"{POST_MARKER} {post.permalink}",
        )
        db.add(message)
        await db.commit()
        try:
            external_id = await sender.send_post(post)
        except SendError as exc:
            await db.delete(message)
            await db.commit()
            if exc.endpoint_dead:
                return
            logger.warning("post share failed for conversation %s: %s", conversation.id, exc)
            continue
        message.external_id = external_id
        await db.commit()


# ---------------------------------------------------------------------------- helpers


STORY_REPLY_MARKER = "[story_reply]"


async def _with_story_note(db: AsyncSession, shop_id: uuid.UUID, story_id: str, text: str) -> str:
    """A reply to a story the bot published: tell the bot what that story was about."""
    note = await db.scalar(
        select(ScheduledStory.note).where(
            ScheduledStory.shop_id == shop_id, ScheduledStory.ig_media_id == story_id
        )
    )
    if not note or not note.strip():
        return text
    about = " ".join(note.split())[:300]
    return text.replace(STORY_REPLY_MARKER, f"[story_reply: {about}]", 1)


async def _lookup_username(
    db: AsyncSession,
    conversation: Conversation,
    account: InstagramAccount,
    instagram: InstagramClient,
) -> None:
    try:
        username = await instagram.get_customer_username(
            decrypt_secret(account.access_token_encrypted), conversation.customer_id
        )
    except InstagramError as exc:
        logger.info("username lookup failed for %s: %s", conversation.customer_id, exc)
        username = None
    conversation.customer_username = (username or "")[:64]
    await db.commit()


async def message_exists(db: AsyncSession, external_id: str) -> bool:
    return (
        await db.scalar(select(Message.id).where(Message.external_id == external_id))
    ) is not None


async def get_or_create_conversation(
    db: AsyncSession, shop_id: uuid.UUID, channel: Channel, channel_ref: str, customer_id: str
) -> Conversation:
    query = select(Conversation).where(
        Conversation.shop_id == shop_id,
        Conversation.channel == channel,
        Conversation.channel_ref == channel_ref,
        Conversation.customer_id == customer_id,
    )
    conversation = await db.scalar(query)
    if conversation is not None:
        return conversation
    conversation = Conversation(
        shop_id=shop_id, channel=channel, channel_ref=channel_ref, customer_id=customer_id
    )
    db.add(conversation)
    try:
        await db.commit()
    except IntegrityError:  # created concurrently by another job
        await db.rollback()
        conversation = await db.scalar(query)
        assert conversation is not None
    return conversation


async def _commit_ignoring_duplicate(db: AsyncSession) -> bool:
    """Commit; False if a concurrent job already stored the same message id."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


# ---------------------------------------------------------------------------- owner replies


async def send_owner_reply(
    db: AsyncSession,
    shop: Shop,
    conversation: Conversation,
    text: str,
    instagram: InstagramClient | None,
) -> str | None:
    """Send the owner's own answer (typed in the panel) on the conversation's channel.

    Returns a user-facing error, or None on success.
    """
    sender = await sender_for(db, shop, conversation, Gateways(instagram=instagram))
    if sender is None:
        return "This channel isn't connected right now; answer the customer in the app itself."
    last = conversation.last_customer_message_at
    if sender.reply_window and last and utcnow() - as_utc(last) > sender.reply_window:
        return (
            "More than 24 hours have passed since the customer's message; "
            "the channel no longer allows a reply."
        )
    external_id = None
    for chunk in split_text(text, sender.max_text_length):
        try:
            external_id = await sender.send_text(chunk)
        except SendError:
            return "Sending the message failed; try again in a moment."
    await record_owner_message(db, shop, conversation, text=text, external_id=external_id)
    return None
