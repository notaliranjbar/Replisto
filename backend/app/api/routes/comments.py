"""Comments on the shop's posts and reels: what the bot answered, and what waits for the owner."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentShop, DbSession, HttpClient, Instagram, JobQueue
from app.core.config import get_settings
from app.core.i18n import localize
from app.models import (
    CommentCategory,
    CommentStatus,
    InstagramAccount,
    InstagramComment,
)
from app.services import comments
from app.services.instagram import SCOPE_COMMENTS
from app.services.llm import LLMError
from app.services.responder import CommentInput, get_responder

router = APIRouter(prefix="/comments", tags=["comments"])

View = Literal["waiting", "answered", "skipped", "all"]
_VIEWS: dict[str, list[CommentStatus]] = {
    "waiting": [CommentStatus.UNANSWERED, CommentStatus.PENDING],
    "answered": [CommentStatus.ANSWERED, CommentStatus.OWNER_REPLIED],
    "skipped": [CommentStatus.SKIPPED, CommentStatus.DISMISSED],
}


class CommentOut(BaseModel):
    id: uuid.UUID
    author_username: str
    text: str
    commented_at: datetime
    status: CommentStatus
    category: CommentCategory | None
    # Why it waits for the owner, in the panel's language.
    reason: str | None
    public_reply: str | None
    private_reply: str | None
    private_reply_sent: bool
    hidden: bool
    is_reply: bool
    post_permalink: str | None
    post_caption: str
    post_preview_url: str | None
    post_kind: Literal["post", "reel", "ad"]
    error: str | None
    handled_at: datetime | None


class CommentCounts(BaseModel):
    waiting: int
    answered: int
    skipped: int
    # Comments waiting for the owner, by category ("none": not sorted, e.g. replies were off).
    waiting_by_category: dict[str, int]


class CommentsOut(BaseModel):
    # Instagram connected with permission to manage comments.
    available: bool
    # Connected, but before comments were part of the permissions: reconnect to grant it.
    needs_reconnect: bool
    counts: CommentCounts
    items: list[CommentOut]


class OwnerReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=900)
    # True: as a private DM to the commenter; False: a public reply under the comment.
    private: bool = False


class HideIn(BaseModel):
    hidden: bool


class TryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    post_caption: str = Field(default="", max_length=2200)
    post_kind: Literal["post", "reel"] = "post"


class TryOut(BaseModel):
    decision: Literal["answer", "unknown", "ignore"]
    category: CommentCategory
    public_reply: str
    private_reply: str
    reason: str | None
    # What the bot looked up in the product list.
    product_lookups: list[dict]
    ai_ready: bool


def _out(c: InstagramComment) -> CommentOut:
    return CommentOut(
        id=c.id,
        author_username=c.author_username,
        text=c.text,
        commented_at=c.commented_at,
        status=c.status,
        category=c.category,
        reason=localize(c.reason),
        public_reply=c.public_reply,
        private_reply=c.private_reply,
        private_reply_sent=c.private_reply_sent,
        hidden=c.hidden,
        is_reply=c.parent_ig_id is not None,
        post_permalink=c.media_permalink,
        post_caption=c.media_caption[:300],
        post_preview_url=c.media_preview_url,
        post_kind=comments._post_kind(c.media_product_type),  # type: ignore[arg-type]
        error=localize(c.error),
        handled_at=c.handled_at,
    )


async def _counts(db: DbSession, shop_id: uuid.UUID) -> CommentCounts:
    rows = (
        await db.execute(
            select(InstagramComment.status, InstagramComment.category, func.count())
            .where(InstagramComment.shop_id == shop_id)
            .group_by(InstagramComment.status, InstagramComment.category)
        )
    ).all()
    counts = {"waiting": 0, "answered": 0, "skipped": 0}
    by_category: dict[str, int] = {}
    for state, category, n in rows:
        for view, states in _VIEWS.items():
            if state in states:
                counts[view] += n
        if state in _VIEWS["waiting"] and state != CommentStatus.PENDING:
            key = category.value if category else "none"
            by_category[key] = by_category.get(key, 0) + n
    return CommentCounts(**counts, waiting_by_category=by_category)


@router.get("", response_model=CommentsOut)
async def list_comments(
    shop: CurrentShop,
    db: DbSession,
    view: View = "waiting",
    category: str | None = None,
    limit: int = 100,
) -> CommentsOut:
    account = await db.scalar(select(InstagramAccount).where(InstagramAccount.shop_id == shop.id))
    query = select(InstagramComment).where(InstagramComment.shop_id == shop.id)
    if view != "all":
        query = query.where(InstagramComment.status.in_(_VIEWS[view]))
    if category == "none":
        query = query.where(InstagramComment.category.is_(None))
    elif category:
        try:
            query = query.where(InstagramComment.category == CommentCategory(category))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown category") from None
    items = (
        await db.scalars(
            query.order_by(InstagramComment.commented_at.desc()).limit(min(max(limit, 1), 200))
        )
    ).all()
    connected = account is not None and account.is_active
    return CommentsOut(
        available=connected and account.has_scope(SCOPE_COMMENTS),
        needs_reconnect=connected and not account.has_scope(SCOPE_COMMENTS),
        counts=await _counts(db, shop.id),
        items=[_out(c) for c in items],
    )


async def _own_comment(
    db: DbSession, shop_id: uuid.UUID, comment_id: uuid.UUID
) -> InstagramComment:
    comment = await db.get(InstagramComment, comment_id)
    if comment is None or comment.shop_id != shop_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    return comment


@router.post("/{comment_id}/reply", response_model=CommentOut)
async def reply(
    comment_id: uuid.UUID,
    body: OwnerReplyIn,
    shop: CurrentShop,
    db: DbSession,
    instagram: Instagram,
) -> CommentOut:
    """The owner's own answer, under the comment or as a private DM."""
    comment = await _own_comment(db, shop.id, comment_id)
    error = await comments.owner_reply(
        db, shop, comment, body.text.strip(), body.private, instagram
    )
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, localize(error))
    return _out(comment)


@router.post("/{comment_id}/dismiss", response_model=CommentOut)
async def dismiss(comment_id: uuid.UUID, shop: CurrentShop, db: DbSession) -> CommentOut:
    """Take it off the waiting list without replying."""
    comment = await _own_comment(db, shop.id, comment_id)
    comment.status = CommentStatus.DISMISSED
    await db.commit()
    return _out(comment)


@router.post("/{comment_id}/hide", response_model=CommentOut)
async def hide(
    comment_id: uuid.UUID, body: HideIn, shop: CurrentShop, db: DbSession, instagram: Instagram
) -> CommentOut:
    """Hide (or show again) a comment; hidden comments stay visible to their author."""
    comment = await _own_comment(db, shop.id, comment_id)
    error = await comments.set_hidden(db, shop, comment, body.hidden, instagram)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, localize(error))
    return _out(comment)


@router.post("/{comment_id}/retry", response_model=CommentOut)
async def retry(
    comment_id: uuid.UUID, shop: CurrentShop, db: DbSession, queue: JobQueue
) -> CommentOut:
    """Let the bot try again (after the owner added the missing information)."""
    comment = await _own_comment(db, shop.id, comment_id)
    if comment.status not in (CommentStatus.UNANSWERED, CommentStatus.DISMISSED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This comment was already answered")
    comment.status = CommentStatus.PENDING
    comment.reason = None
    comment.error = None
    await db.commit()
    await queue.enqueue(
        "answer_comment", str(comment.id), job_id=f"answer-comment:{comment.id}:{uuid.uuid4().hex}"
    )
    return _out(comment)


@router.post("/try", response_model=TryOut)
async def try_comment(body: TryIn, shop: CurrentShop, db: DbSession, http: HttpClient) -> TryOut:
    """What the bot would do with this comment, in the shop's current comment mode (nothing
    is posted or charged)."""
    simple = comments.needs_no_ai(body.text)
    if simple is not None:
        answer = comments.simple_answer(shop, simple)
    else:
        try:
            answer = await get_responder(db, http).answer_comment(
                shop,
                CommentInput(
                    text=body.text, post_caption=body.post_caption, post_kind=body.post_kind
                ),
            )
        except LLMError:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The AI service isn't responding right now. Please try again in a moment.",
            ) from None
    public, private = comments.plan_replies(shop, answer)
    return TryOut(
        decision=answer.decision,
        category=answer.category,
        public_reply=public,
        private_reply=private,
        reason=localize(answer.reason),
        product_lookups=answer.tool_trace,
        ai_ready=get_settings().llm_configured,
    )
