import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class KnowledgeSection(enum.StrEnum):
    ABOUT = "about"
    SHIPPING = "shipping"
    PAYMENT = "payment"
    RETURNS = "returns"
    CONTACT = "contact"
    FAQ = "faq"
    FREE_TEXT = "free_text"
    FILE = "file"


class KnowledgeEntry(UUIDPk, Timestamps, Base):
    """A piece of static shop knowledge (shipping policy, an FAQ pair, extracted file text...)."""

    __tablename__ = "knowledge_entries"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[KnowledgeSection] = mapped_column(str_enum(KnowledgeSection))
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text)
    source_filename: Mapped[str | None] = mapped_column(String(255))


class ProductSourceKind(enum.StrEnum):
    GOOGLE_SHEET = "google_sheet"
    UPLOAD = "upload"


class ProductSource(UUIDPk, Timestamps, Base):
    """Where a shop's product/stock table comes from. Google Sheets are re-synced periodically."""

    __tablename__ = "product_sources"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), unique=True
    )
    kind: Mapped[ProductSourceKind] = mapped_column(str_enum(ProductSourceKind))
    url: Mapped[str | None] = mapped_column(Text)
    # Maps our canonical fields (name, color, size, price, stock...) to the sheet's column headers.
    column_mapping: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)


class ProductOrigin(enum.StrEnum):
    """How Replisto learned about a product. Every product lives in Replisto's own catalogue."""

    MANUAL = "manual"  # typed in the panel or edited by hand
    SHEET = "sheet"  # a live Google Sheet; re-synced, so edit it in the sheet
    FILE = "file"  # an uploaded Excel/CSV table
    TEACH = "teach"  # understood by the AI from text, a document or a link


class Product(UUIDPk, Timestamps, Base):
    """One sellable variant: a row per product × colour × size combination."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_shop_name", "shop_id", "name"),)

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[ProductOrigin] = mapped_column(
        str_enum(ProductOrigin),
        default=ProductOrigin.MANUAL,
        server_default=ProductOrigin.MANUAL.value,
    )
    # The sheet/file the row was imported from; a re-sync replaces only that source's rows.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_sources.id", ondelete="SET NULL"), index=True
    )
    # Public photo of the product (shown in the panel).
    image_url: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120))
    color: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[str | None] = mapped_column(String(64))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # In the shop's currency
    stock: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    # Any extra sheet columns we don't model explicitly, kept so the bot can still use them.
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # Instagram post of this product, if the owner put its link in the product sheet.
    post_url: Mapped[str | None] = mapped_column(Text)
