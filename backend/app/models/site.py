from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk


class SiteChatUsage(UUIDPk, Timestamps, Base):
    """AI tokens used per day by the website assistant, per visitor/user/IP (and in total).

    `key` is "v:<visitor id>", "u:<user id>", "ip:<address>" or "all:guests"; `day` is the
    UTC date. The daily allowances are in settings (SITE_CHAT_*).
    """

    __tablename__ = "site_chat_usage"
    __table_args__ = (UniqueConstraint("key", "day"),)

    key: Mapped[str] = mapped_column(String(80))
    day: Mapped[str] = mapped_column(String(10))
    tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    messages: Mapped[int] = mapped_column(default=0)
