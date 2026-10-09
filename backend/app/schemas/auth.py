import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)
    shop_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    bot_enabled: bool
    tone: str
    use_emoji: bool
    fallback_message: str
    forbidden_rules: str
    handoff_pause_minutes: int
    # ISO 4217 code of the product prices' currency (USD, LBP, ...).
    currency: str
    # The owner's panel language; the panel keeps it in sync.
    language: Literal["en", "ar"]
    # The owner's time zone (IANA name, from the browser).
    timezone: str
    # Comments: "off", "public", "private" (a DM to the commenter) or "both".
    comment_mode: Literal["off", "public", "private", "both"]
    comment_thank_praise: bool
    comment_hide_spam: bool


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    bot_enabled: bool | None = None
    tone: Literal["friendly", "formal"] | None = None
    use_emoji: bool | None = None
    fallback_message: str | None = Field(default=None, min_length=1, max_length=1000)
    forbidden_rules: str | None = Field(default=None, max_length=4000)
    handoff_pause_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    language: Literal["en", "ar"] | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=40)
    comment_mode: Literal["off", "public", "private", "both"] | None = None
    comment_thank_praise: bool | None = None
    comment_hide_spam: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown time zone") from None
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    email_verified_at: datetime | None
    # Verified mobile number in E.164 form (+96170123456), or null.
    phone: str | None
    phone_verified_at: datetime | None
    shop: ShopOut
