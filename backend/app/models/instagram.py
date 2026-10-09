import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk

if TYPE_CHECKING:
    from app.models.user import Shop


class InstagramAccount(UUIDPk, Timestamps, Base):
    __tablename__ = "instagram_accounts"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), unique=True
    )
    # Instagram professional account ID; webhooks are routed to a shop by this value.
    ig_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    posts_synced_at: Mapped[datetime | None] = mapped_column()
    # Permissions the owner granted, comma separated (instagram_business_manage_comments, ...).
    # Accounts connected before a permission existed have to reconnect to grant it.
    scopes: Mapped[str] = mapped_column(Text, default="", server_default="")

    shop: Mapped["Shop"] = relationship(back_populates="instagram_account")

    def has_scope(self, scope: str) -> bool:
        return scope in {s.strip() for s in self.scopes.split(",")}


class InstagramPost(UUIDPk, Timestamps, Base):
    """A post from the shop's own Instagram feed, read so the bot can share it in a DM."""

    __tablename__ = "instagram_posts"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    # Instagram media id: what the Send API needs to share the post as a native card.
    ig_media_id: Mapped[str] = mapped_column(String(64))
    permalink: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text, default="")
    media_type: Mapped[str] = mapped_column(String(32), default="")
    # Image to show in the panel (thumbnail for videos).
    preview_url: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column()
