"""Replisto's own assistant on the website: visitors ask about Replisto and see the bot at work.

It is an ordinary shop (marked `is_house`, see scripts/seed_house.py) answering on the "web"
channel, so
everything the product does applies to us too: the team teaches it from the panel, unknown
questions are handed to the team (an email alert, a reply from the panel inbox), and
off-topic questions get the canned redirect. It isn't charged to any wallet.

What protects us from abuse is a daily AI-token allowance, shown to the visitor as a ring:

    guest   (not logged in) ── SITE_CHAT_GUEST_TOKENS per visitor id
                            ── SITE_CHAT_IP_TOKENS per IP (all guests behind it)
                            ── SITE_CHAT_DAILY_TOKENS for all guests together
    member  (logged in)     ── SITE_CHAT_MEMBER_TOKENS per user

plus a per-minute message limit and short messages. Days are UTC days.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models import Channel, Conversation, Message, MessageSender, Shop, SiteChatUsage, User

# A typical answer of the site assistant, before we've seen any (for "about N answers left").
DEFAULT_TOKENS_PER_ANSWER = 4_000
HISTORY_SHOWN = 40


class SiteChatError(Exception):
    """User-facing reason (English; translated where it reaches the visitor)."""


@dataclass
class Quota:
    tier: str  # "guest" | "member"
    used: int
    limit: int
    # Which allowance ran out: None, "personal", "network" (the IP) or "everyone" (all guests).
    exhausted: str | None
    resets_at: datetime
    tokens_per_answer: int

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def left_percent(self) -> int:
        if self.exhausted and self.exhausted != "personal":
            return 0
        return round(100 * self.left / self.limit) if self.limit else 0

    @property
    def answers_left(self) -> int:
        if self.exhausted:
            return 0
        return self.left // max(1, self.tokens_per_answer)


def _today() -> tuple[str, datetime]:
    now = utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return now.date().isoformat(), midnight


def keys_for(user: User | None, visitor: str, ip: str) -> dict[str, tuple[str, int]]:
    """The allowances this request counts against: name -> (usage key, daily limit)."""
    settings = get_settings()
    if user is not None:
        return {"personal": (f"u:{user.id}", settings.site_chat_member_tokens)}
    return {
        "personal": (f"v:{visitor}", settings.site_chat_guest_tokens),
        "network": (f"ip:{ip}", settings.site_chat_ip_tokens),
        "everyone": ("all:guests", settings.site_chat_daily_tokens),
    }


async def _used(db: AsyncSession, key: str, day: str) -> int:
    value = await db.scalar(
        select(SiteChatUsage.tokens).where(SiteChatUsage.key == key, SiteChatUsage.day == day)
    )
    return int(value or 0)


async def quota(
    db: AsyncSession, user: User | None, visitor: str, ip: str, tokens_per_answer: int
) -> Quota:
    day, resets_at = _today()
    exhausted = None
    personal_used = personal_limit = 0
    for name, (key, limit) in keys_for(user, visitor, ip).items():
        used = await _used(db, key, day)
        if name == "personal":
            personal_used, personal_limit = used, limit
        if used >= limit and exhausted is None:
            exhausted = name
    return Quota(
        tier="member" if user is not None else "guest",
        used=personal_used,
        limit=personal_limit,
        exhausted=exhausted,
        resets_at=resets_at,
        tokens_per_answer=tokens_per_answer,
    )


async def spend(db: AsyncSession, user: User | None, visitor: str, ip: str, tokens: int) -> None:
    day, _ = _today()
    for key, _limit in keys_for(user, visitor, ip).values():
        exists = await db.scalar(
            select(SiteChatUsage.id).where(SiteChatUsage.key == key, SiteChatUsage.day == day)
        )
        if exists is None:
            db.add(SiteChatUsage(key=key, day=day, tokens=0, messages=0))
            try:
                await db.commit()
            except IntegrityError:  # created by a parallel request
                await db.rollback()
        await db.execute(
            update(SiteChatUsage)
            .where(SiteChatUsage.key == key, SiteChatUsage.day == day)
            .values(tokens=SiteChatUsage.tokens + tokens, messages=SiteChatUsage.messages + 1)
        )
    await db.commit()


async def house_shop(db: AsyncSession) -> Shop | None:
    shop = await db.scalar(select(Shop).where(Shop.is_house.is_(True)).limit(1))
    return shop if shop is not None and shop.bot_enabled else None


def customer_id_for(user: User | None, visitor: str) -> str:
    return f"u:{user.id}" if user is not None else f"v:{visitor}"


def valid_visitor(visitor: str) -> str:
    try:
        return str(uuid.UUID(visitor))
    except ValueError:
        raise SiteChatError("This chat link isn't valid. Please reload the page.") from None


async def find_conversation(
    db: AsyncSession, shop: Shop, user: User | None, visitor: str
) -> Conversation | None:
    return await db.scalar(
        select(Conversation).where(
            Conversation.shop_id == shop.id,
            Conversation.channel == Channel.WEB,
            Conversation.channel_ref == "",
            Conversation.customer_id == customer_id_for(user, visitor),
        )
    )


async def messages_of(db: AsyncSession, conversation: Conversation | None) -> list[Message]:
    if conversation is None:
        return []
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_SHOWN)
        )
    ).all()
    return list(reversed(rows))


async def tokens_per_answer(db: AsyncSession, conversation: Conversation | None) -> int:
    """Average tokens of this conversation's answers (or a typical value)."""
    if conversation is None:
        return DEFAULT_TOKENS_PER_ANSWER
    rows = (
        await db.execute(
            select(Message.prompt_tokens, Message.completion_tokens)
            .where(
                Message.conversation_id == conversation.id,
                Message.sender == MessageSender.BOT,
                Message.prompt_tokens.is_not(None),
                Message.off_topic.is_(False),
            )
            .order_by(Message.created_at.desc())
            .limit(10)
        )
    ).all()
    totals = [(p or 0) + (c or 0) for p, c in rows]
    return round(sum(totals) / len(totals)) if totals else DEFAULT_TOKENS_PER_ANSWER
