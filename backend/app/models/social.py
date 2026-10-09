"""Instagram beyond DMs: comments the bot answers, stories it publishes, and page insights."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class CommentStatus(enum.StrEnum):
    PENDING = "pending"  # just arrived; the bot is on it
    ANSWERED = "answered"  # the bot replied (publicly, privately or both)
    # A real question the shop's information doesn't cover: no reply, it waits for the owner.
    UNANSWERED = "unanswered"
    OWNER_REPLIED = "owner_replied"
    SKIPPED = "skipped"  # nothing to answer: friends tagged, spam, unrelated
    DISMISSED = "dismissed"  # the owner cleared it from the waiting list


class CommentCategory(enum.StrEnum):
    PRICE = "price"
    AVAILABILITY = "availability"  # stock, sizes, colours
    PRODUCT = "product"  # details, materials, recommendations
    ORDER = "order"  # how to order, delivery, payment
    COMPLAINT = "complaint"
    PRAISE = "praise"
    SPAM = "spam"
    OTHER = "other"


class InstagramComment(UUIDPk, Timestamps, Base):
    """A comment on one of the shop's posts or reels."""

    __tablename__ = "instagram_comments"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    ig_comment_id: Mapped[str] = mapped_column(String(64), unique=True)
    # Set when this comment is a reply inside another comment's thread.
    parent_ig_id: Mapped[str | None] = mapped_column(String(64))
    # The post or reel it was written under, and what we know of it (the caption tells the
    # bot which product "price?" is about).
    media_id: Mapped[str] = mapped_column(String(64), default="")
    media_permalink: Mapped[str | None] = mapped_column(Text)
    media_caption: Mapped[str] = mapped_column(Text, default="")
    media_preview_url: Mapped[str | None] = mapped_column(Text)
    media_product_type: Mapped[str] = mapped_column(String(16), default="")
    # The commenter's Instagram-scoped id: the same id their DMs come from.
    author_id: Mapped[str] = mapped_column(String(64))
    author_username: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    commented_at: Mapped[datetime] = mapped_column()

    status: Mapped[CommentStatus] = mapped_column(
        str_enum(CommentStatus), default=CommentStatus.PENDING, index=True
    )
    category: Mapped[CommentCategory | None] = mapped_column(str_enum(CommentCategory))
    # Why the bot left it for the owner, in the owner's language.
    reason: Mapped[str | None] = mapped_column(String(255))
    public_reply: Mapped[str | None] = mapped_column(Text)
    public_reply_id: Mapped[str | None] = mapped_column(String(64))
    private_reply: Mapped[str | None] = mapped_column(Text)
    private_reply_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    handled_at: Mapped[datetime | None] = mapped_column()
    # The last delivery problem, shown to the owner.
    error: Mapped[str | None] = mapped_column(String(255))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)


class StoryStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    # Handed to Instagram; videos are processed for a while before they can be published.
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class ScheduledStory(UUIDPk, Timestamps, Base):
    """A story the owner uploaded for the bot to publish at a set time."""

    __tablename__ = "scheduled_stories"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    media_kind: Mapped[str] = mapped_column(String(8))  # image | video
    # The file under MEDIA_DIR/stories, served to Instagram at a URL carrying `token`.
    file_name: Mapped[str] = mapped_column(String(96))
    content_type: Mapped[str] = mapped_column(String(48))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    token: Mapped[str] = mapped_column(String(48))
    # What the story is about, in the owner's words. When customers reply to the story, the
    # bot reads this to know what they're replying to.
    note: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[StoryStatus] = mapped_column(
        str_enum(StoryStatus), default=StoryStatus.SCHEDULED, index=True
    )
    container_id: Mapped[str | None] = mapped_column(String(64))
    ig_media_id: Mapped[str | None] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class InstagramInsights(UUIDPk, Timestamps, Base):
    """The latest numbers read from Instagram for a shop's page (one row per shop)."""

    __tablename__ = "instagram_insights"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), unique=True
    )
    # profile, this week's and last week's totals, daily series and recent posts with their
    # numbers; see services/insights.py.
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    fetched_at: Mapped[datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(String(255))


class ContentReport(UUIDPk, Timestamps, Base):
    """The content assistant's analysis of the page: what works, ideas, a weekly plan."""

    __tablename__ = "content_reports"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(2), default="en")
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
