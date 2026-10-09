"""The "Ask Replisto" chat on the website (public; logging in raises the daily allowance)."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, HttpClient, OptionalUser
from app.core.throttle import Throttle
from app.core.timeutil import utcnow
from app.models import Channel, Message, MessageSender, User
from app.services import messaging, site_chat
from app.services.llm import LLMError
from app.services.notify import EmailNotifier
from app.services.responder import get_responder

router = APIRouter(prefix="/site", tags=["site"])

_per_visitor = Throttle(6, 60)
_per_ip = Throttle(20, 60)


class SiteMessageOut(BaseModel):
    id: uuid.UUID
    # "owner" is a person from the Replisto team answering in the same chat.
    sender: Literal["customer", "bot", "owner"]
    text: str
    created_at: datetime


class QuotaOut(BaseModel):
    """Today's AI allowance, for the ring next to the chat."""

    tier: Literal["guest", "member"]
    used_tokens: int
    limit_tokens: int
    left_percent: int
    # Roughly how many more answers fit (from this chat's average answer size).
    answers_left: int
    # None, or which allowance ran out: "personal", "network" (shared IP) or "everyone".
    exhausted: str | None
    resets_at: datetime


class SiteChatOut(BaseModel):
    # False when the assistant isn't set up on this server.
    available: bool
    messages: list[SiteMessageOut]
    quota: QuotaOut
    # The question went to the team; their answer appears here (poll while this is true).
    waiting_for_team: bool


class SiteChatIn(BaseModel):
    # A random id the browser keeps (crypto.randomUUID()), so a guest's chat survives reloads.
    visitor: str = Field(min_length=36, max_length=36)
    text: str = Field(min_length=1, max_length=600)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _visitor(raw: str) -> str:
    try:
        return site_chat.valid_visitor(raw)
    except site_chat.SiteChatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


async def _state(db: DbSession, user: User | None, visitor: str, ip: str) -> SiteChatOut:
    shop = await site_chat.house_shop(db)
    conversation = (
        await site_chat.find_conversation(db, shop, user, visitor) if shop is not None else None
    )
    messages = await site_chat.messages_of(db, conversation)
    quota = await site_chat.quota(
        db, user, visitor, ip, await site_chat.tokens_per_answer(db, conversation)
    )
    return SiteChatOut(
        available=shop is not None,
        messages=[
            SiteMessageOut(id=m.id, sender=m.sender.value, text=m.text, created_at=m.created_at)
            for m in messages
        ],
        quota=QuotaOut(
            tier=quota.tier,  # type: ignore[arg-type]
            used_tokens=quota.used,
            limit_tokens=quota.limit,
            left_percent=quota.left_percent,
            answers_left=quota.answers_left,
            exhausted=quota.exhausted,
            resets_at=quota.resets_at,
        ),
        waiting_for_team=bool(conversation and conversation.handoff_open),
    )


@router.get("/chat", response_model=SiteChatOut)
async def get_chat(
    request: Request, db: DbSession, user: OptionalUser, visitor: str = Query(min_length=36)
) -> SiteChatOut:
    """The chat so far and today's allowance. The widget polls this while waiting."""
    return await _state(db, user, _visitor(visitor), _ip(request))


@router.post("/chat", response_model=SiteChatOut)
async def send(
    body: SiteChatIn, request: Request, db: DbSession, http: HttpClient, user: OptionalUser
) -> SiteChatOut:
    visitor = _visitor(body.visitor)
    ip = _ip(request)
    shop = await site_chat.house_shop(db)
    if shop is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant isn't available right now."
        )

    personal = site_chat.customer_id_for(user, visitor)
    if _per_visitor.blocked(personal) or _per_ip.blocked(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "A little slower please, try again in a few seconds."
        )
    conversation = await site_chat.find_conversation(db, shop, user, visitor)
    quota = await site_chat.quota(
        db, user, visitor, ip, await site_chat.tokens_per_answer(db, conversation)
    )
    if quota.exhausted:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Today's chat allowance is used up. Create a free account for more."
            if user is None
            else "Today's chat allowance is used up.",
        )
    _per_visitor.hit(personal)
    _per_ip.hit(ip)

    if conversation is None:
        conversation = await messaging.get_or_create_conversation(
            db, shop.id, Channel.WEB, "", personal
        )
    if user is not None:
        conversation.customer_name = (user.full_name or user.email)[:128]
        conversation.customer_username = user.email[:64]
    elif not conversation.customer_name:
        conversation.customer_name = "Website visitor"
    now = utcnow()
    db.add(
        Message(
            conversation_id=conversation.id,
            sender=MessageSender.CUSTOMER,
            text=body.text.strip(),
            external_id=f"web:{uuid.uuid4()}",
        )
    )
    conversation.last_customer_message_at = now
    await db.commit()

    try:
        await messaging.reply_to_conversation(
            db, conversation.id, now, None, get_responder(db, http), notifier=EmailNotifier(db)
        )
    except LLMError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is busy right now, please ask again in a moment.",
        ) from None

    # This request's answer(s): what it cost counts against today's allowance.
    answers = (
        await db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.sender == MessageSender.BOT,
                Message.created_at >= now,
            )
        )
    ).all()
    tokens = sum((m.prompt_tokens or 0) + (m.completion_tokens or 0) for m in answers)
    await site_chat.spend(db, user, visitor, ip, tokens)
    return await _state(db, user, visitor, ip)
