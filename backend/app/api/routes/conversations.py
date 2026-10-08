"""The panel's inbox: conversations, handoffs to the owner, bot pause, unanswered list."""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, exists, func, or_, select

from app.api.deps import CurrentShop, DbSession, HttpClient
from app.core.timeutil import as_utc, utcnow
from app.models import Channel, Conversation, HandoffResolution, Message, MessageSender, Shop
from app.services.instagram import InstagramClient
from app.services.messaging import send_owner_reply

router = APIRouter(tags=["conversations"])

# "Pause until I resume" is stored as a far-future time so there is one code path.
_INDEFINITE = timedelta(days=3650)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sender: MessageSender
    text: str
    unanswered: bool
    created_at: datetime


class HandoffOut(BaseModel):
    """The bot passed this conversation to the owner (latest handoff)."""

    # open: the customer is waiting for the owner. resolved: the owner replied or closed it.
    status: Literal["open", "resolved"]
    handed_off_at: datetime
    # Short reason written by the bot, e.g. "The customer wants a formal invoice".
    reason: str | None
    # What the customer asked; grows if they keep writing while waiting.
    question: str
    resolved_at: datetime | None
    resolved_by: HandoffResolution | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    channel: Channel
    # The customer's id on the channel (Instagram IGSID).
    customer_id: str
    # Same as customer_id; kept for older panel builds.
    customer_igsid: str
    customer_username: str | None
    # Display name where the channel gives one.
    customer_name: str | None
    # Opens the chat with the customer in the channel's app, for replying by hand.
    chat_url: str | None
    # Instagram only (same as chat_url there); kept for older panel builds.
    instagram_url: str | None
    last_customer_message_at: datetime | None
    bot_paused_until: datetime | None
    bot_paused: bool
    open_unanswered: int
    handoff: HandoffOut | None
    last_message: MessageOut | None


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    total: int


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class PauseIn(BaseModel):
    # Omit (null) to pause until resumed by hand.
    minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)


class HandoffItem(BaseModel):
    conversation_id: uuid.UUID
    channel: Channel
    customer_igsid: str
    customer_username: str | None
    customer_name: str | None
    chat_url: str | None
    instagram_url: str | None
    last_customer_message_at: datetime | None
    handoff: HandoffOut


class HandoffPage(BaseModel):
    items: list[HandoffItem]
    total: int


class UnansweredOut(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    customer_username: str | None
    # What the customer asked (the customer messages just before the bot gave up).
    question: str
    created_at: datetime


def _open_unanswered():
    return and_(Message.unanswered.is_(True), Message.unanswered_resolved.is_(False))


def _handoff_is_open():
    return and_(Conversation.handoff_at.is_not(None), Conversation.handoff_resolved_at.is_(None))


@router.get("/conversations", response_model=ConversationPage)
async def list_conversations(
    shop: CurrentShop,
    db: DbSession,
    filter: Literal["all", "needs_owner", "unanswered", "paused"] = "all",
    channel: Channel | None = None,
    q: str | None = Query(default=None, max_length=64, description="customer username or name"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> ConversationPage:
    query = select(Conversation).where(Conversation.shop_id == shop.id)
    if filter == "needs_owner":
        query = query.where(_handoff_is_open())
    elif filter == "unanswered":
        query = query.where(
            exists().where(Message.conversation_id == Conversation.id, _open_unanswered())
        )
    elif filter == "paused":
        query = query.where(Conversation.bot_paused_until > utcnow())
    if channel is not None:
        query = query.where(Conversation.channel == channel)
    if q:
        query = query.where(
            or_(
                Conversation.customer_username.ilike(f"%{q}%"),
                Conversation.customer_name.ilike(f"%{q}%"),
                Conversation.customer_id == q,
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    conversations = (
        await db.scalars(
            query.order_by(
                func.coalesce(Conversation.last_customer_message_at, Conversation.created_at).desc()
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return ConversationPage(
        items=[await _conversation_out(db, c) for c in conversations], total=total or 0
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, shop: CurrentShop, db: DbSession
) -> ConversationDetail:
    conversation = await _get(db, shop, conversation_id)
    messages = list(
        reversed(
            (
                await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(200)
                )
            ).all()
        )
    )
    base = await _conversation_out(db, conversation)
    return ConversationDetail(
        **base.model_dump(), messages=[MessageOut.model_validate(m) for m in messages]
    )


@router.post("/conversations/{conversation_id}/reply", response_model=ConversationOut)
async def reply(
    conversation_id: uuid.UUID,
    body: ReplyIn,
    shop: CurrentShop,
    db: DbSession,
    http: HttpClient,
) -> ConversationOut:
    """The owner answers the customer from the panel, on the conversation's channel.

    Counts as the owner's own reply: the bot steps back and an open handoff is closed.
    """
    conversation = await _get(db, shop, conversation_id)
    error = await send_owner_reply(db, shop, conversation, body.text.strip(), InstagramClient(http))
    if error:
        raise HTTPException(status.HTTP_409_CONFLICT, error)
    await db.refresh(conversation)
    return await _conversation_out(db, conversation)


@router.post("/conversations/{conversation_id}/pause", response_model=ConversationOut)
async def pause_bot(
    conversation_id: uuid.UUID, body: PauseIn, shop: CurrentShop, db: DbSession
) -> ConversationOut:
    """Stop the bot for this one customer (e.g. the owner is handling it)."""
    conversation = await _get(db, shop, conversation_id)
    duration = timedelta(minutes=body.minutes) if body.minutes else _INDEFINITE
    conversation.bot_paused_until = utcnow() + duration
    await db.commit()
    return await _conversation_out(db, conversation)


@router.post("/conversations/{conversation_id}/resume", response_model=ConversationOut)
async def resume_bot(
    conversation_id: uuid.UUID, shop: CurrentShop, db: DbSession
) -> ConversationOut:
    conversation = await _get(db, shop, conversation_id)
    conversation.bot_paused_until = None
    await db.commit()
    return await _conversation_out(db, conversation)


@router.get("/handoffs", response_model=HandoffPage)
async def list_handoffs(
    shop: CurrentShop,
    db: DbSession,
    status_filter: Literal["open", "resolved"] = Query(default="open", alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> HandoffPage:
    """DMs the bot passed to the owner because it didn't know the answer.

    Open ones come oldest first (the customer who has waited longest is on top); resolved
    ones newest first. A handoff resolves itself when the owner replies to the customer.
    """
    query = select(Conversation).where(Conversation.shop_id == shop.id)
    if status_filter == "open":
        query = query.where(_handoff_is_open()).order_by(Conversation.handoff_at)
    else:
        query = query.where(Conversation.handoff_resolved_at.is_not(None)).order_by(
            Conversation.handoff_resolved_at.desc()
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    conversations = (await db.scalars(query.offset(offset).limit(limit))).all()
    items = []
    for conversation in conversations:
        handoff = _handoff_out(conversation)
        assert handoff is not None
        items.append(
            HandoffItem(
                conversation_id=conversation.id,
                channel=conversation.channel,
                customer_igsid=conversation.customer_id,
                customer_username=conversation.customer_username or None,
                customer_name=conversation.customer_name,
                chat_url=_chat_url(conversation),
                instagram_url=_instagram_url(conversation),
                last_customer_message_at=conversation.last_customer_message_at,
                handoff=handoff,
            )
        )
    return HandoffPage(items=items, total=total or 0)


@router.post("/handoffs/{conversation_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_handoff(conversation_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> None:
    """Close a handoff by hand (e.g. the owner answered by phone). Idempotent."""
    conversation = await _get(db, shop, conversation_id)
    if conversation.handoff_open:
        conversation.handoff_resolved_at = utcnow()
        conversation.handoff_resolved_by = HandoffResolution.MANUAL
        await db.commit()


@router.get("/unanswered", response_model=list[UnansweredOut])
async def list_unanswered(
    shop: CurrentShop, db: DbSession, limit: int = Query(default=50, ge=1, le=200)
) -> list[UnansweredOut]:
    """Questions the bot couldn't answer from the shop's data. Newest first.

    The panel shows these as "add this to your information" suggestions.
    """
    rows = (
        await db.execute(
            select(Message, Conversation)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.shop_id == shop.id, _open_unanswered())
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).all()
    items = []
    for message, conversation in rows:
        items.append(
            UnansweredOut(
                message_id=message.id,
                conversation_id=conversation.id,
                customer_username=conversation.customer_username or None,
                question=await _question_for(db, message),
                created_at=message.created_at,
            )
        )
    return items


@router.post("/unanswered/{message_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_unanswered(message_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> None:
    message = await db.get(Message, message_id)
    conversation = await db.get(Conversation, message.conversation_id) if message else None
    if message is None or conversation is None or conversation.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    message.unanswered_resolved = True
    await db.commit()


async def _question_for(db: DbSession, message: Message) -> str:
    if message.sender == MessageSender.CUSTOMER:
        return message.text
    earlier = (
        await db.scalars(
            select(Message)
            .where(
                Message.conversation_id == message.conversation_id,
                Message.created_at < message.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(5)
        )
    ).all()
    asked = []
    for m in earlier:
        if m.sender != MessageSender.CUSTOMER:
            break
        asked.append(m.text)
    return "\n".join(reversed(asked))


async def _get(db: DbSession, shop: Shop, conversation_id: uuid.UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


def _instagram_url(conversation: Conversation) -> str | None:
    if conversation.channel == Channel.INSTAGRAM and conversation.customer_username:
        return f"https://ig.me/m/{conversation.customer_username}"
    return None


def _chat_url(conversation: Conversation) -> str | None:
    return _instagram_url(conversation)


def _handoff_out(conversation: Conversation) -> HandoffOut | None:
    if conversation.handoff_at is None:
        return None
    return HandoffOut(
        status="open" if conversation.handoff_open else "resolved",
        handed_off_at=conversation.handoff_at,
        reason=conversation.handoff_reason,
        question=conversation.handoff_question or "",
        resolved_at=conversation.handoff_resolved_at,
        resolved_by=conversation.handoff_resolved_by,
    )


async def _conversation_out(db: DbSession, conversation: Conversation) -> ConversationOut:
    last = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    open_count = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation.id, _open_unanswered())
    )
    paused_until = conversation.bot_paused_until
    return ConversationOut(
        id=conversation.id,
        channel=conversation.channel,
        customer_id=conversation.customer_id,
        customer_igsid=conversation.customer_id,
        customer_username=conversation.customer_username or None,
        customer_name=conversation.customer_name,
        chat_url=_chat_url(conversation),
        instagram_url=_instagram_url(conversation),
        last_customer_message_at=conversation.last_customer_message_at,
        bot_paused_until=paused_until,
        bot_paused=paused_until is not None and as_utc(paused_until) > utcnow(),
        open_unanswered=open_count or 0,
        handoff=_handoff_out(conversation),
        last_message=MessageOut.model_validate(last) if last else None,
    )
