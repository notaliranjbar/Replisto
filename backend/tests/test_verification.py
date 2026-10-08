"""Email and phone verification, the sign-up gift, and the login rate limit."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models import GiftClaim, Shop, User, WalletEntry, WalletEntryKind
from app.services import gifts, phone
from app.services.accounts import delete_user

REGISTER = {"email": "new@shop.ir", "password": "strongpass1", "shop_name": "S"}


async def _gifts(db: AsyncSession, shop: Shop) -> list[WalletEntry]:
    return list(
        (
            await db.scalars(
                select(WalletEntry).where(
                    WalletEntry.shop_id == shop.id, WalletEntry.kind == WalletEntryKind.BONUS
                )
            )
        ).all()
    )


async def _owner(db: AsyncSession, email: str, number: str | None = None) -> User:
    user = User(email=email, password_hash="x", phone=number)
    user.phone_verified_at = utcnow() if number else None
    user.shop = Shop(name="S")
    db.add(user)
    await db.commit()
    return user


# ---------------------------------------------------------------------------- the gift


async def test_gift_after_verifying_the_phone(db: AsyncSession, billing_on: None) -> None:
    user = await _owner(db, "a@shop.ir")
    assert await gifts.check(db, user.shop) == 0  # no verified number yet
    assert await _gifts(db, user.shop) == []

    user.phone, user.phone_verified_at = "+989121234567", utcnow()
    await db.commit()
    credit = get_settings().signup_credit_rial
    assert await gifts.check(db, user.shop) == credit
    await db.refresh(user.shop)
    assert user.shop.balance_rial == credit and user.shop.signup_gift_at is not None

    # Checking again changes nothing.
    assert await gifts.check(db, user.shop) == 0
    assert len(await _gifts(db, user.shop)) == 1


async def test_one_gift_per_number(db: AsyncSession, billing_on: None) -> None:
    """Deleting the account and signing up again with the same number pays nothing."""
    first = await _owner(db, "a@shop.ir", "+989121234567")
    assert await gifts.check(db, first.shop) > 0
    await delete_user(db, first.id)

    second = await _owner(db, "b@shop.ir", "+989121234567")
    assert await gifts.check(db, second.shop) == 0
    assert await _gifts(db, second.shop) == []
    # Stored as hashes only: no number in the table.
    keys = (await db.scalars(select(GiftClaim.key))).all()
    assert keys and all("9121234567" not in k for k in keys)


# ---------------------------------------------------------------------------- phone by SMS


@pytest.fixture
def sms(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def fake_send(http, number: str, code: str) -> None:  # type: ignore[no-untyped-def]
        sent.append((number, code))

    monkeypatch.setattr(phone, "send_code", fake_send)
    return sent


async def _register(client: AsyncClient, **extra: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/register", json={**REGISTER, **extra})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_phone_verification_by_sms(
    client: AsyncClient, sms: list[tuple[str, str]], billing_on: None
) -> None:
    headers = await _register(client)
    resp = await client.post("/api/v1/me/phone", json={"phone": "۰۹۱۲ ۱۲۳ ۴۵۶۷"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone"] == "09121234567"
    assert sms[0][0] == "+989121234567"
    code = sms[0][1]

    wrong = "000000" if code != "000000" else "111111"
    resp = await client.post("/api/v1/me/phone/verify", json={"code": wrong}, headers=headers)
    assert resp.status_code == 400
    resp = await client.post("/api/v1/me/phone/verify", json={"code": code}, headers=headers)
    assert resp.status_code == 200, resp.text
    # A verified number earns the sign-up gift.
    gift = get_settings().signup_credit_rial // 10
    assert resp.json() == {"phone": "09121234567", "gift_toman": gift}
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["phone"] == "+989121234567" and me["phone_verified_at"]

    # A second code within the minute is refused.
    resp = await client.post("/api/v1/me/phone", json={"phone": "09121234568"}, headers=headers)
    assert resp.status_code == 429


async def test_phone_codes_are_checked(
    client: AsyncClient, sms: list[tuple[str, str]], db: AsyncSession
) -> None:
    headers = await _register(client)
    resp = await client.post("/api/v1/me/phone", json={"phone": "12345"}, headers=headers)
    assert resp.status_code == 400  # not a mobile number

    await client.post("/api/v1/me/phone", json={"phone": "09121234567"}, headers=headers)
    for _ in range(phone.MAX_CODE_ATTEMPTS):
        await client.post("/api/v1/me/phone/verify", json={"code": "999999x"}, headers=headers)
    resp = await client.post("/api/v1/me/phone/verify", json={"code": sms[0][1]}, headers=headers)
    assert resp.status_code == 400  # too many wrong tries: ask for a new code

    other = await _register(client, email="other@shop.ir")
    user = await db.scalar(select(User).where(User.email == "new@shop.ir"))
    assert user is not None
    user.phone, user.phone_verified_at = "+989121234567", utcnow()
    await db.commit()
    resp = await client.post("/api/v1/me/phone", json={"phone": "09121234567"}, headers=other)
    assert resp.status_code == 400 and "حساب دیگری" in resp.json()["detail"]


def test_normalizing_numbers() -> None:
    assert phone.normalize_iran_mobile("+98 912-123-4567") == "+989121234567"
    assert phone.normalize_iran_mobile("00989121234567") == "+989121234567"
    assert phone.normalize_iran_mobile("9121234567") == "+989121234567"
    with pytest.raises(phone.PhoneError):
        phone.normalize_iran_mobile("02112345678")  # a landline
    assert phone.local_format("+989121234567") == "09121234567"


# ---------------------------------------------------------------------------- email


async def test_email_verification(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import auth

    mails: list[tuple[str, str]] = []

    async def fake_send(to: str, subject: str, body: str) -> None:
        mails.append((to, body))

    monkeypatch.setattr(auth, "send_email", fake_send)
    monkeypatch.setattr(get_settings(), "require_verified_email", True)
    headers = await _register(client)
    assert mails and mails[0][0] == "new@shop.ir"
    token = mails[0][1].split("token=")[1].split()[0]
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["email_verified_at"] is None
    # The panel stays closed until the link is clicked
    assert (await client.get("/api/v1/shop", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/dashboard", headers=headers)).status_code == 403

    bad = await client.post("/api/v1/auth/email/verify", json={"token": token[:-3] + "abc"})
    assert bad.status_code == 400
    resp = await client.post("/api/v1/auth/email/verify", json={"token": token})
    assert resp.status_code == 204
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["email_verified_at"] is not None
    assert (await client.get("/api/v1/shop", headers=headers)).status_code == 200
    resp = await client.post("/api/v1/auth/email/resend", headers=headers)
    assert "قبلا تأیید" in resp.json()["message"]


async def test_resending_the_verification_email_is_limited(client: AsyncClient) -> None:
    headers = await _register(client)
    assert (await client.post("/api/v1/auth/email/resend", headers=headers)).status_code == 202
    assert (await client.post("/api/v1/auth/email/resend", headers=headers)).status_code == 429


# ---------------------------------------------------------------------------- login


async def test_wrong_passwords_lock_the_login_for_a_while(client: AsyncClient) -> None:
    await _register(client)
    wrong = {"email": REGISTER["email"], "password": "wrongpass1"}
    for _ in range(get_settings().login_max_failures):
        assert (await client.post("/api/v1/auth/login", json=wrong)).status_code == 401
    right = {"email": REGISTER["email"], "password": REGISTER["password"]}
    resp = await client.post("/api/v1/auth/login", json=right)
    assert resp.status_code == 429 and "دقیقه" in resp.json()["detail"]
    # Another account from elsewhere is unaffected by this email's lock.
    await _register(client, email="b@shop.ir")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "b@shop.ir", "password": REGISTER["password"]}
    )
    assert resp.status_code == 200


async def test_a_successful_login_clears_the_failures(client: AsyncClient) -> None:
    await _register(client)
    wrong = {"email": REGISTER["email"], "password": "wrongpass1"}
    right = {"email": REGISTER["email"], "password": REGISTER["password"]}
    for _ in range(get_settings().login_max_failures - 1):
        await client.post("/api/v1/auth/login", json=wrong)
    assert (await client.post("/api/v1/auth/login", json=right)).status_code == 200
    for _ in range(get_settings().login_max_failures - 1):
        await client.post("/api/v1/auth/login", json=wrong)
    assert (await client.post("/api/v1/auth/login", json=right)).status_code == 200
