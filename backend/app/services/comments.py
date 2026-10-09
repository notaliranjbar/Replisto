"""Comments on the shop's posts and reels.

    comments webhook ──► record_comment ──(enqueue)──► answer_comment ──► Instagram
                                                            │
                                     unanswered / skipped ◄──┘ (listed in the panel)

- The bot answers from the shop's information only. In the shop's comment mode it replies
  under the comment, in a private DM to the commenter, or both (the answer by DM and a short
  public note).
- If the information doesn't cover the question it doesn't reply at all: the comment waits
  in the panel, grouped by category (price, availability, complaint, ...), for the owner.
- Friends tagged, emoji, spam and chatter are skipped; spam can be hidden automatically.
- Each answered comment is charged to the wallet like a DM answer. Skipped and unanswered
  comments aren't.
- A private reply also lands in the commenter's DM thread (as a bot message), so when they
  answer there the bot knows what it already told them.
"""

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.queue import Queue
from app.core.security import decrypt_secret
from app.core.timeutil import utcnow
from app.models import (
    Channel,
    CommentCategory,
    CommentStatus,
    InstagramAccount,
    InstagramComment,
    InstagramPost,
    Message,
    MessageSender,
    Shop,
)
from app.services import billing
from app.services.instagram import MAX_TEXT_LENGTH, InstagramClient, InstagramError
from app.services.llm import LLMError
from app.services.messaging import get_or_create_conversation
from app.services.responder import CommentAnswer, CommentInput, Responder
from app.services.webhook import CommentEvent

logger = logging.getLogger(__name__)

COMMENT_MODES = ("off", "public", "private", "both")
# How a commenter's comment shows in their DM thread with the shop.
COMMENT_MARKER = "[comment]"
# Instagram allows comment replies up to 2,200 characters; we keep public replies short.
MAX_PUBLIC_REPLY = 900

# Reasons the owner reads next to a waiting comment (translated in the panel's language).
REASON_OFF = "Comment replies are switched off"
REASON_BOT_OFF = "The bot is switched off"
REASON_EMPTY_WALLET = "The Replisto wallet is empty"
REASON_NOT_CONNECTED = "Instagram isn't connected"
REASON_SEND_FAILED = "Instagram didn't accept the reply"

_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
_MENTION = re.compile(r"@[\w.]+")


# ---------------------------------------------------------------------------- incoming


async def record_comment(
    db: AsyncSession,
    event: CommentEvent,
    queue: Queue,
    instagram: InstagramClient | None = None,
) -> InstagramComment | None:
    """Store a new comment with its post's context and schedule the bot's answer."""
    if not get_settings().instagram_enabled:
        return None
    account = await db.scalar(
        select(InstagramAccount).where(
            InstagramAccount.ig_user_id == event.account_ig_id,
            InstagramAccount.is_active.is_(True),
        )
    )
    if account is None:
        logger.info("comment for unknown or inactive account %s", event.account_ig_id)
        return None
    if await db.scalar(
        select(InstagramComment.id).where(InstagramComment.ig_comment_id == event.comment_id)
    ):
        return None

    comment = InstagramComment(
        shop_id=account.shop_id,
        ig_comment_id=event.comment_id,
        parent_ig_id=event.parent_id,
        media_id=event.media_id,
        media_product_type=event.media_product_type,
        author_id=event.author_id,
        author_username=event.author_username[:64],
        text=event.text,
        commented_at=event.timestamp,
    )
    await _attach_post(db, comment, account, instagram)
    db.add(comment)
    try:
        await db.commit()
    except IntegrityError:  # the same comment, recorded concurrently
        await db.rollback()
        return None
    await queue.enqueue("answer_comment", str(comment.id), job_id=f"answer-comment:{comment.id}")
    return comment


async def _attach_post(
    db: AsyncSession,
    comment: InstagramComment,
    account: InstagramAccount,
    instagram: InstagramClient | None,
) -> None:
    """The caption and picture of the post the comment is under."""
    if not comment.media_id:
        return
    post = await db.scalar(
        select(InstagramPost).where(
            InstagramPost.shop_id == account.shop_id,
            InstagramPost.ig_media_id == comment.media_id,
        )
    )
    if post is not None:
        comment.media_caption = post.caption
        comment.media_permalink = post.permalink
        comment.media_preview_url = post.preview_url
        return
    if instagram is None:
        return
    try:
        media = await instagram.get_media(
            decrypt_secret(account.access_token_encrypted), comment.media_id
        )
    except InstagramError as exc:
        logger.info("couldn't read media %s: %s", comment.media_id, exc)
        return
    comment.media_caption = (media.get("caption") or "")[:5000]
    comment.media_permalink = media.get("permalink")
    comment.media_preview_url = media.get("thumbnail_url") or media.get("media_url")
    comment.media_product_type = comment.media_product_type or str(
        media.get("media_product_type") or ""
    )


# ---------------------------------------------------------------------------- answering


def needs_no_ai(text: str) -> CommentCategory | None:
    """Comments the bot can sort without the AI: only emoji (praise) or only @mentions."""
    without_mentions = _MENTION.sub("", text).strip()
    if _LETTERS.search(without_mentions) or any(ch.isdigit() for ch in without_mentions):
        return None
    if _MENTION.search(text) and not without_mentions:
        return CommentCategory.OTHER  # friends tagging friends
    return CommentCategory.PRAISE if without_mentions else CommentCategory.OTHER


def simple_answer(shop: Shop, category: CommentCategory) -> CommentAnswer:
    """The no-AI answer: a heart for emoji praise (when thanking is on), otherwise nothing."""
    if category == CommentCategory.PRAISE and shop.comment_thank_praise and shop.use_emoji:
        return CommentAnswer("answer", category, public_reply="🙏🤍")
    return CommentAnswer("ignore", category)


def plan_replies(shop: Shop, answer: CommentAnswer) -> tuple[str, str]:
    """(public, private) as the shop's comment mode wants them; praise only ever gets a
    public thank-you."""
    if answer.decision != "answer":
        return "", ""
    public = answer.public_reply.strip()
    private = answer.private_reply.strip()
    if answer.category == CommentCategory.PRAISE or shop.comment_mode == "public":
        return (public or private)[:MAX_PUBLIC_REPLY], ""
    if shop.comment_mode == "private":
        return "", (private or public)[:MAX_TEXT_LENGTH]
    if not private:  # "both", but only a public answer came back: send it privately
        return "", public[:MAX_TEXT_LENGTH]
    return public[:MAX_PUBLIC_REPLY], private[:MAX_TEXT_LENGTH]


async def answer_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    instagram: InstagramClient,
    responder: Responder,
) -> None:
    """The bot's turn on a comment. Raises retryable Instagram/AI errors for the worker."""
    comment = await db.get(InstagramComment, comment_id)
    if comment is None or comment.status != CommentStatus.PENDING:
        return
    shop = await db.get(Shop, comment.shop_id)
    account = await db.scalar(
        select(InstagramAccount).where(InstagramAccount.shop_id == comment.shop_id)
    )
    if shop is None:
        return
    if account is None or not account.is_active:
        await _leave_for_owner(db, comment, None, REASON_NOT_CONNECTED)
        return
    if shop.comment_mode not in COMMENT_MODES[1:]:
        await _leave_for_owner(db, comment, None, REASON_OFF)
        return
    if not shop.bot_enabled:
        await _leave_for_owner(db, comment, None, REASON_BOT_OFF)
        return

    token = decrypt_secret(account.access_token_encrypted)
    simple = needs_no_ai(comment.text)
    if simple is not None:
        answer = simple_answer(shop, simple)
        if answer.decision == "answer":
            await _deliver(db, shop, comment, answer, instagram, token, charge=False)
            return
        comment.status = CommentStatus.SKIPPED
        comment.category = simple
        comment.handled_at = utcnow()
        await db.commit()
        return

    if not billing.can_spend(shop):
        await _leave_for_owner(db, comment, None, REASON_EMPTY_WALLET)
        return

    try:
        answer = await responder.answer_comment(
            shop,
            CommentInput(
                text=comment.text,
                username=comment.author_username,
                post_caption=comment.media_caption,
                post_kind=_post_kind(comment.media_product_type),
            ),
        )
    except LLMError as exc:
        if exc.retryable:
            raise
        logger.error("LLM rejected comment for shop %s: %s", shop.id, exc)
        await _leave_for_owner(db, comment, None, "The AI couldn't read this comment")
        return

    comment.prompt_tokens = answer.prompt_tokens
    comment.completion_tokens = answer.completion_tokens
    if answer.decision == "ignore":
        comment.status = CommentStatus.SKIPPED
        comment.category = answer.category
        comment.handled_at = utcnow()
        await db.commit()
        if answer.category == CommentCategory.SPAM and shop.comment_hide_spam:
            await _hide(db, comment, instagram, token)
        return
    if answer.decision == "unknown":
        await _leave_for_owner(db, comment, answer.category, answer.reason)
        return
    await _deliver(db, shop, comment, answer, instagram, token, charge=True)


async def _deliver(
    db: AsyncSession,
    shop: Shop,
    comment: InstagramComment,
    answer: CommentAnswer,
    instagram: InstagramClient,
    token: str,
    *,
    charge: bool,
) -> None:
    """Send the replies the shop's comment mode calls for."""
    public, private = plan_replies(shop, answer)
    comment.category = answer.category
    sent_any = False
    try:
        if private:
            await _send_private(db, shop, comment, private, instagram, token)
            sent_any = True
        if public:
            comment.public_reply = public
            comment.public_reply_id = await instagram.reply_to_comment(
                token, comment.ig_comment_id, public
            )
            sent_any = True
    except InstagramError as exc:
        if exc.retryable and not sent_any:
            await db.rollback()
            raise
        logger.warning("comment reply failed for %s: %s", comment.id, exc)
        comment.error = REASON_SEND_FAILED
        if not sent_any:
            await _leave_for_owner(db, comment, answer.category, REASON_SEND_FAILED)
            return
    comment.status = CommentStatus.ANSWERED
    comment.handled_at = utcnow()
    await db.commit()
    if charge:
        await billing.charge_usage(
            db,
            shop,
            prompt_tokens=answer.prompt_tokens,
            completion_tokens=answer.completion_tokens,
            description="Comment reply on Instagram",
            details={"comment_id": str(comment.id)},
        )


async def _send_private(
    db: AsyncSession,
    shop: Shop,
    comment: InstagramComment,
    text: str,
    instagram: InstagramClient,
    token: str,
) -> None:
    """A private reply, recorded in the commenter's DM thread before it is sent (its echo
    then matches it instead of looking like the owner typing)."""
    text = text[:MAX_TEXT_LENGTH]
    conversation = await get_or_create_conversation(
        db, shop.id, Channel.INSTAGRAM, "", comment.author_id
    )
    if conversation.customer_username is None and comment.author_username:
        conversation.customer_username = comment.author_username
    if not await db.scalar(
        select(Message.id).where(Message.external_id == f"comment:{comment.ig_comment_id}")
    ):
        db.add(
            Message(
                conversation_id=conversation.id,
                sender=MessageSender.CUSTOMER,
                text=f"{COMMENT_MARKER} {comment.text}"[:4000],
                external_id=f"comment:{comment.ig_comment_id}",
            )
        )
    message = Message(conversation_id=conversation.id, sender=MessageSender.BOT, text=text)
    db.add(message)
    await db.commit()
    try:
        message.external_id = await instagram.send_private_reply(token, comment.ig_comment_id, text)
    except InstagramError:
        await db.delete(message)
        await db.commit()
        raise
    comment.private_reply = text
    comment.private_reply_sent = True
    await db.commit()


async def _leave_for_owner(
    db: AsyncSession,
    comment: InstagramComment,
    category: CommentCategory | None,
    reason: str | None,
) -> None:
    comment.status = CommentStatus.UNANSWERED
    comment.category = category or comment.category
    comment.reason = (reason or "")[:255] or None
    comment.handled_at = utcnow()
    await db.commit()


async def _hide(
    db: AsyncSession, comment: InstagramComment, instagram: InstagramClient, token: str
) -> None:
    try:
        await instagram.hide_comment(token, comment.ig_comment_id, True)
    except InstagramError as exc:
        logger.info("couldn't hide comment %s: %s", comment.id, exc)
        return
    comment.hidden = True
    await db.commit()


def _post_kind(product_type: str) -> str:
    kind = product_type.upper()
    if kind == "REELS":
        return "reel"
    if kind == "AD":
        return "ad"
    return "post"


# ---------------------------------------------------------------------------- the owner


async def owner_reply(
    db: AsyncSession,
    shop: Shop,
    comment: InstagramComment,
    text: str,
    private: bool,
    instagram: InstagramClient,
) -> str | None:
    """The owner answers a comment from the panel. Returns a user-facing error or None."""
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    if account is None or not account.is_active:
        return "Connect your Instagram account first."
    token = decrypt_secret(account.access_token_encrypted)
    try:
        if private:
            if comment.private_reply_sent:
                return "Instagram allows only one private reply per comment."
            await _send_private(db, shop, comment, text, instagram, token)
        else:
            comment.public_reply = text[:MAX_PUBLIC_REPLY]
            comment.public_reply_id = await instagram.reply_to_comment(
                token, comment.ig_comment_id, comment.public_reply
            )
    except InstagramError as exc:
        logger.warning("owner comment reply failed for %s: %s", comment.id, exc)
        await db.rollback()
        return (
            "Instagram didn't accept the reply. Private replies work within 7 days of the comment."
        )
    comment.status = CommentStatus.OWNER_REPLIED
    comment.error = None
    comment.handled_at = utcnow()
    await db.commit()
    return None


async def set_hidden(
    db: AsyncSession,
    shop: Shop,
    comment: InstagramComment,
    hidden: bool,
    instagram: InstagramClient,
) -> str | None:
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    if account is None or not account.is_active:
        return "Connect your Instagram account first."
    try:
        await instagram.hide_comment(
            decrypt_secret(account.access_token_encrypted), comment.ig_comment_id, hidden
        )
    except InstagramError as exc:
        logger.warning("hide comment failed for %s: %s", comment.id, exc)
        return "Instagram didn't accept the change. Please try again."
    comment.hidden = hidden
    await db.commit()
    return None
