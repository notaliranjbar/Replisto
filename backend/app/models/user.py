import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk

if TYPE_CHECKING:
    from app.models.instagram import InstagramAccount


FALLBACK_MESSAGES = {
    "en": "Thanks for your message! A teammate will get back to you shortly 🙏",
    "ar": "شكرًا لرسالتك! سيتواصل معك أحد زملائنا قريبًا 🙏",
}


def default_fallback(language: str) -> str:
    """The shop's first handoff message, in the owner's language."""
    return FALLBACK_MESSAGES.get(language, FALLBACK_MESSAGES["en"])


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set when the owner opened the link we emailed them.
    email_verified_at: Mapped[datetime | None] = mapped_column()
    # A verified mobile number in E.164 form (+14155550123), confirmed with an SMS code. One
    # number belongs to one account.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column()
    # The SMS code waiting to be typed in: the number it went to, its hash and lifetime.
    phone_pending: Mapped[str | None] = mapped_column(String(20))
    phone_code_hash: Mapped[str | None] = mapped_column(String(64))
    phone_code_expires_at: Mapped[datetime | None] = mapped_column()
    phone_code_attempts: Mapped[int] = mapped_column(default=0, server_default="0")

    shop: Mapped["Shop"] = relationship(back_populates="owner", uselist=False)


class Shop(UUIDPk, Timestamps, Base):
    """The tenant. Everything the bot knows and does is scoped to a shop."""

    __tablename__ = "shops"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(120))

    # Bot behaviour settings
    bot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tone: Mapped[str] = mapped_column(String(16), default="friendly")  # friendly | formal
    use_emoji: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_message: Mapped[str] = mapped_column(Text, default=FALLBACK_MESSAGES["en"])
    forbidden_rules: Mapped[str] = mapped_column(Text, default="")
    # How long the bot stays silent in a thread after the owner replies manually.
    handoff_pause_minutes: Mapped[int] = mapped_column(default=120)

    # The currency the shop's product prices are in (ISO 4217: USD, LBP, ...).
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    # The owner's panel language ("en" or "ar"); what the bot writes for the owner (handoff
    # reasons, summaries of what it learned) is in this language.
    language: Mapped[str] = mapped_column(String(2), default="en", server_default="en")

    # Billing: a prepaid wallet in US cents. Every AI answer is deducted from it.
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # When we last told the owner the wallet is low / empty (so we don't repeat it).
    low_balance_notified_at: Mapped[datetime | None] = mapped_column()
    empty_wallet_notified_at: Mapped[datetime | None] = mapped_column()
    # The sign-up gift is given once, after the owner verifies their mobile number; see
    # services/gifts.py.
    signup_gift_at: Mapped[datetime | None] = mapped_column()
    # Replisto's own shop: the assistant on our website ("Ask Replisto"). It answers about
    # Replisto and is never charged. Set by scripts/seed_house.py; at most one.
    is_house: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    owner: Mapped[User] = relationship(back_populates="shop")
    instagram_account: Mapped["InstagramAccount | None"] = relationship(
        back_populates="shop", uselist=False
    )
