import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
)
from app.core.timeutil import utcnow
from app.models import InstagramAccount, Shop, User
from app.services.instagram_accounts import refresh_expiring_tokens
from tests.conftest import FakeMeta


async def _connect(client: AsyncClient, headers: dict[str, str], code: str = "good-code"):
    url = (await client.get("/api/v1/instagram/connect-url", headers=headers)).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return await client.get(
        "/api/v1/instagram/callback", params={"code": f"{code}#_", "state": state}
    )


def _redirect_params(resp) -> dict[str, str]:
    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://panel.test/instagram/callback"
    )
    return {k: v[0] for k, v in parse_qs(location.query).items()}


async def test_connect_url(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assert (await client.get("/api/v1/instagram/connect-url")).status_code == 401
    url = (await client.get("/api/v1/instagram/connect-url", headers=auth_headers)).json()["url"]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "www.instagram.com"
    assert query["client_id"] == ["ig-app-id"]
    assert query["redirect_uri"] == ["https://api.test/api/v1/instagram/callback"]
    assert "instagram_business_manage_messages" in query["scope"][0]


async def test_connect_flow(
    client: AsyncClient, auth_headers: dict[str, str], fake_meta: FakeMeta, db: AsyncSession
) -> None:
    resp = await _connect(client, auth_headers)
    assert resp.status_code == 302
    assert _redirect_params(resp) == {"status": "connected"}
    assert fake_meta.subscribed

    status = (await client.get("/api/v1/instagram", headers=auth_headers)).json()
    assert status["connected"] and status["active"]
    assert status["username"] == "layla.boutique"
    assert status["ig_user_id"] == fake_meta.ig_user_id

    account = await db.scalar(select(InstagramAccount))
    assert account is not None
    assert "long-token" not in account.access_token_encrypted  # stored encrypted

    assert (await client.delete("/api/v1/instagram", headers=auth_headers)).status_code == 204
    status = (await client.get("/api/v1/instagram", headers=auth_headers)).json()
    assert status == {
        "available": True,
        "connected": False,
        "active": False,
        "username": None,
        "ig_user_id": None,
        "token_expires_at": None,
    }


async def test_callback_rejects_forged_state(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/instagram/callback", params={"code": "good-code", "state": "forged"}
    )
    assert _redirect_params(resp) == {"status": "error", "reason": "invalid_state"}


async def test_callback_rejects_access_token_as_state(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # A leaked access token must not be usable as an OAuth state.
    access = auth_headers["Authorization"].removeprefix("Bearer ")
    resp = await client.get(
        "/api/v1/instagram/callback", params={"code": "good-code", "state": access}
    )
    assert _redirect_params(resp)["reason"] == "invalid_state"


async def test_callback_user_denied(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/instagram/callback",
        params={"error": "access_denied", "error_reason": "user_denied"},
    )
    assert _redirect_params(resp) == {"status": "denied"}


async def test_callback_instagram_error(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await _connect(client, auth_headers, code="bad-code")
    assert _redirect_params(resp) == {"status": "error", "reason": "instagram"}


async def test_same_page_cannot_join_two_shops(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _connect(client, auth_headers)
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@shop.com", "password": "strongpass1", "shop_name": "Other"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    resp = await _connect(client, other_headers)
    assert _redirect_params(resp) == {"status": "error", "reason": "account_in_use"}


async def test_reconnect_same_page_updates_token(
    client: AsyncClient, auth_headers: dict[str, str], db: AsyncSession
) -> None:
    await _connect(client, auth_headers)
    resp = await _connect(client, auth_headers)
    assert _redirect_params(resp) == {"status": "connected"}
    assert len((await db.scalars(select(InstagramAccount))).all()) == 1


async def _make_account(db: AsyncSession, email: str, ig_id: str, expires_in: timedelta):
    user = User(email=email, password_hash="x")
    user.shop = Shop(name=email)
    db.add(user)
    await db.flush()
    account = InstagramAccount(
        shop_id=user.shop.id,
        ig_user_id=ig_id,
        username=email,
        access_token_encrypted=encrypt_secret("old-token"),
        token_expires_at=utcnow() + expires_in,
    )
    db.add(account)
    await db.commit()
    return account


async def test_refresh_expiring_tokens(db: AsyncSession, fake_meta: FakeMeta) -> None:
    soon = await _make_account(db, "a@x.com", "1", timedelta(days=3))
    later = await _make_account(db, "b@x.com", "2", timedelta(days=40))
    later_token = later.access_token_encrypted

    assert await refresh_expiring_tokens(db, fake_meta.client()) == 1
    await db.refresh(soon)
    await db.refresh(later)
    assert decrypt_secret(soon.access_token_encrypted) == "refreshed-token"
    assert later.access_token_encrypted == later_token


async def test_refresh_revoked_token_deactivates(db: AsyncSession, fake_meta: FakeMeta) -> None:
    account = await _make_account(db, "a@x.com", "1", timedelta(days=1))
    fake_meta.refresh_error = (400, {"error": {"message": "Session invalid", "code": 190}})
    assert await refresh_expiring_tokens(db, fake_meta.client()) == 0
    await db.refresh(account)
    assert account.is_active is False


def test_state_token_is_scoped() -> None:
    state = create_token(uuid.uuid4(), "ig_oauth")
    with pytest.raises(TokenError):
        decode_token(state, "access")
