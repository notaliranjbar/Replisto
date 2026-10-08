from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentShop, CurrentUser, DbSession, HttpClient, SignedInUser
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.core.throttle import Throttle, minutes_text
from app.models import Shop, User
from app.schemas.auth import ShopOut, ShopUpdate, UserOut
from app.services import gifts, phone
from app.services.accounts import delete_user

router = APIRouter(tags=["account"])

# SMS codes cost money and can annoy whoever owns the number: one a minute per account, and
# a few an hour per number.
_sms_per_user = Throttle(1, 60)
_sms_per_phone = Throttle(4, 3600)
_sms_per_user_day = Throttle(10, 24 * 3600)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AccountDelete(BaseModel):
    password: str


class PhoneStart(BaseModel):
    phone: str = Field(min_length=1, max_length=30)


class PhoneConfirm(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class PhoneStartOut(BaseModel):
    phone: str  # where the code went, as Iranians write it (09...)
    minutes: int  # how long the code works


class PhoneVerifiedOut(BaseModel):
    phone: str
    # Sign-up gift given because of this (0 if none).
    gift_toman: int


@router.get("/me", response_model=UserOut)
async def me(user: SignedInUser) -> User:
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, user: CurrentUser, db: DbSession) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز عبور فعلی اشتباه است")
    user.password_hash = hash_password(body.new_password)
    await db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(body: AccountDelete, user: SignedInUser, db: DbSession) -> None:
    """Permanently delete the account and everything stored for it (Meta requires this)."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "رمز عبور اشتباه است")
    await delete_user(db, user.id)


@router.get("/shop", response_model=ShopOut)
async def get_shop(shop: CurrentShop) -> Shop:
    return shop


@router.patch("/shop", response_model=ShopOut)
async def update_shop(body: ShopUpdate, shop: CurrentShop, db: DbSession) -> Shop:
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(shop, field, value)
    await db.commit()
    await db.refresh(shop)
    return shop


@router.post("/me/phone", response_model=PhoneStartOut)
async def start_phone_verification(
    body: PhoneStart, user: CurrentUser, db: DbSession, http: HttpClient
) -> PhoneStartOut:
    """Text a 6-digit code to this mobile number."""
    try:
        number = phone.normalize_iran_mobile(body.phone)
    except phone.PhoneError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    for throttle, key in (
        (_sms_per_user, str(user.id)),
        (_sms_per_user_day, str(user.id)),
        (_sms_per_phone, number),
    ):
        if throttle.blocked(key):
            wait = minutes_text(throttle.retry_after(key))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, f"لطفا {wait} دیگر دوباره درخواست کد بدهید."
            )
    try:
        number = await phone.start(db, http, user, number)
    except phone.PhoneError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    for throttle, key in (
        (_sms_per_user, str(user.id)),
        (_sms_per_user_day, str(user.id)),
        (_sms_per_phone, number),
    ):
        throttle.hit(key)
    return PhoneStartOut(
        phone=phone.local_format(number), minutes=get_settings().phone_code_minutes
    )


@router.post("/me/phone/verify", response_model=PhoneVerifiedOut)
async def confirm_phone(body: PhoneConfirm, user: CurrentUser, db: DbSession) -> PhoneVerifiedOut:
    try:
        number = await phone.confirm(db, user, body.code)
    except phone.PhoneError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    given = await gifts.check(db, user.shop)
    return PhoneVerifiedOut(phone=phone.local_format(number), gift_toman=given // 10)
