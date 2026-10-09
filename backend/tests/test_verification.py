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
from tests.conftest import FakeWeb

REGISTER = {"email": "new@shop.com", "password": "strongpass1", "shop_name": "S"}


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
    user = await _owner(db, "a@shop.com")
    assert await gifts.check(db, user.shop) == 0  # no verified number yet
    assert await _gifts(db, user.shop) == []

    user.phone, user.phone_verified_at = "+96170123456", utcnow()
    await db.commit()
    credit = get_settings().signup_credit_cents
    assert await gifts.check(db, user.shop) == credit
    await db.refresh(user.shop)
    assert user.shop.balance_cents == credit and user.shop.signup_gift_at is not None

    # Checking again changes nothing.
    assert await gifts.check(db, user.shop) == 0
    assert len(await _gifts(db, user.shop)) == 1


async def test_one_gift_per_number(db: AsyncSession, billing_on: None) -> None:
    """Deleting the account and signing up again with the same number pays nothing."""
    first = await _owner(db, "a@shop.com", "+96170123456")
    assert await gifts.check(db, first.shop) > 0
    await delete_user(db, first.id)

    second = await _owner(db, "b@shop.com", "+96170123456")
    assert await gifts.check(db, second.shop) == 0
    assert await _gifts(db, second.shop) == []
    # Stored as hashes only: no number in the table.
    keys = (await db.scalars(select(GiftClaim.key))).all()
    assert keys and all("70123456" not in k for k in keys)


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
    resp = await client.post("/api/v1/me/phone", json={"phone": "٧٠ ١٢٣ ٤٥٦"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone"] == "+96170123456"
    assert sms[0][0] == "+96170123456"
    code = sms[0][1]

    wrong = "000000" if code != "000000" else "111111"
    resp = await client.post("/api/v1/me/phone/verify", json={"code": wrong}, headers=headers)
    assert resp.status_code == 400
    resp = await client.post("/api/v1/me/phone/verify", json={"code": code}, headers=headers)
    assert resp.status_code == 200, resp.text
    # A verified number earns the sign-up gift.
    gift = get_settings().signup_credit_cents
    assert resp.json() == {"phone": "+96170123456", "gift_cents": gift}
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["phone"] == "+96170123456" and me["phone_verified_at"]

    # A second code within the minute is refused.
    resp = await client.post("/api/v1/me/phone", json={"phone": "70 123 457"}, headers=headers)
    assert resp.status_code == 429


async def test_phone_codes_are_checked(
    client: AsyncClient, sms: list[tuple[str, str]], db: AsyncSession
) -> None:
    headers = await _register(client)
    resp = await client.post("/api/v1/me/phone", json={"phone": "12345"}, headers=headers)
    assert resp.status_code == 400  # not a phone number
    resp = await client.post("/api/v1/me/phone", json={"phone": "01 234 567"}, headers=headers)
    assert resp.status_code == 400 and "70 123 456" in resp.json()["detail"]  # a landline

    await client.post("/api/v1/me/phone", json={"phone": "+96170123456"}, headers=headers)
    for _ in range(phone.MAX_CODE_ATTEMPTS):
        await client.post("/api/v1/me/phone/verify", json={"code": "999999x"}, headers=headers)
    resp = await client.post("/api/v1/me/phone/verify", json={"code": sms[0][1]}, headers=headers)
    assert resp.status_code == 400  # too many wrong tries: ask for a new code

    other = await _register(client, email="other@shop.com")
    user = await db.scalar(select(User).where(User.email == "new@shop.com"))
    assert user is not None
    user.phone, user.phone_verified_at = "+96170123456", utcnow()
    await db.commit()
    resp = await client.post("/api/v1/me/phone", json={"phone": "+96170123456"}, headers=other)
    assert resp.status_code == 400 and "another" in resp.json()["detail"]


def test_normalizing_numbers() -> None:
    # Lebanese numbers as people type them, without +961.
    assert phone.normalize("70 123 456") == "+96170123456"
    assert phone.normalize("03 123 456") == "+9613123456"
    assert phone.normalize("+961 81 123 456") == "+96181123456"
    assert phone.normalize("00961 76 123 456") == "+96176123456"
    assert phone.normalize("٧١-١٢٣-٤٥٦") == "+96171123456"
    # Other countries with their code.
    assert phone.normalize("+1 (415) 555-0123") == "+14155550123"
    assert phone.normalize("+971 50 123 4567") == "+971501234567"
    bad_numbers = ("12345", "01 234 567", "+961 1 234 567", "70 123", "+0123456789", "+1234")
    for bad in bad_numbers:
        with pytest.raises(phone.PhoneError):
            phone.normalize(bad)


async def test_codes_go_out_through_twilio(
    fake_web: FakeWeb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "twilio_account_sid", "AC123")
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "secret")
    monkeypatch.setattr(get_settings(), "twilio_from", "MG456")
    await phone.send_code(fake_web.client(), "+96170123456", "123456")
    [sent] = fake_web.twilio.sent
    assert sent["To"] == "+96170123456" and sent["MessagingServiceSid"] == "MG456"
    assert "123456" in sent["Body"]


# ---------------------------------------------------------------------------- email


async def test_email_verification(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import auth

    mails: list[tuple[str, str]] = []

    async def fake_send(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        mails.append((to, body))

    monkeypatch.setattr(auth, "send_email", fake_send)
    monkeypatch.setattr(get_settings(), "require_verified_email", True)
    headers = await _register(client)
    assert mails and mails[0][0] == "new@shop.com"
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
    assert "already confirmed" in resp.json()["message"]


async def test_resending_the_verification_email_is_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "require_verified_email", True)
    headers = await _register(client)
    assert (await client.post("/api/v1/auth/email/resend", headers=headers)).status_code == 202
    assert (await client.post("/api/v1/auth/email/resend", headers=headers)).status_code == 429


# ---------------------------------------------------------------------------- login


async def test_without_required_verification_accounts_start_verified(
    client: AsyncClient,
) -> None:
    """A test server without email (REQUIRE_VERIFIED_EMAIL=false): no confirmation step."""
    headers = await _register(client)
    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["email_verified_at"] is not None


async def test_wrong_passwords_lock_the_login_for_a_while(client: AsyncClient) -> None:
    await _register(client)
    wrong = {"email": REGISTER["email"], "password": "wrongpass1"}
    for _ in range(get_settings().login_max_failures):
        assert (await client.post("/api/v1/auth/login", json=wrong)).status_code == 401
    right = {"email": REGISTER["email"], "password": REGISTER["password"]}
    resp = await client.post("/api/v1/auth/login", json=right)
    assert resp.status_code == 429 and "minute" in resp.json()["detail"]
    # Another account from elsewhere is unaffected by this email's lock.
    await _register(client, email="b@shop.com")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "b@shop.com", "password": REGISTER["password"]}
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
