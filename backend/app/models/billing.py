import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class WalletEntryKind(enum.StrEnum):
    TOPUP = "topup"  # paid through the gateway
    USAGE = "usage"  # an AI answer (or reading a document for the owner)
    BONUS = "bonus"  # free credit (sign-up gift)
    ADJUSTMENT = "adjustment"  # set by us by hand (support, card-to-card payment, refund)


class WalletEntry(UUIDPk, Timestamps, Base):
    """The wallet ledger: one row per change of a shop's balance. Never edited."""

    __tablename__ = "wallet_entries"
    __table_args__ = (Index("ix_wallet_entries_shop_created", "shop_id", "created_at"),)

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    kind: Mapped[WalletEntryKind] = mapped_column(str_enum(WalletEntryKind))
    # Positive adds credit, negative spends it.
    amount_rial: Mapped[int] = mapped_column(BigInteger)
    balance_after_rial: Mapped[int] = mapped_column(BigInteger)
    # Shown to the owner ("Customer reply on Instagram").
    description: Mapped[str] = mapped_column(String(255), default="")
    # e.g. tokens, conversation id, payment id.
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class Payment(UUIDPk, Timestamps, Base):
    """A wallet top-up through the payment gateway."""

    __tablename__ = "payments"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    gateway: Mapped[str] = mapped_column(String(32), default="zarinpal")
    amount_rial: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    # Gateway's id for the payment session; the callback identifies the payment by it.
    authority: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Bank reference number after a successful payment.
    ref_id: Mapped[str | None] = mapped_column(String(64))
    card_pan: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column()


class GiftClaim(UUIDPk, Timestamps, Base):
    """A phone number that already earned a shop the sign-up gift.

    Kept (as a hash, without the number itself) even when that shop is deleted, so deleting
    and re-creating accounts doesn't earn the gift again.
    """

    __tablename__ = "gift_claims"

    # sha256 of "<kind>:<value>" with our secret (kind is "phone").
    key: Mapped[str] = mapped_column(String(64), unique=True)
    # The shop that got the gift (no foreign key: the claim outlives the shop).
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
