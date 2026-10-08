from httpx import AsyncClient

from app.core.security import create_token, decrypt_secret, encrypt_secret

REGISTER = {
    "email": "Owner@Shop.com",
    "password": "strongpass1",
    "full_name": "Layla",
    "shop_name": "Layla Boutique",
}


async def test_health(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/health/ready")).status_code == 200


async def test_register_creates_user_and_shop(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", json=REGISTER)
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@shop.com"  # normalized
    assert body["shop"]["name"] == "Layla Boutique"
    assert body["shop"]["bot_enabled"] is False


async def test_register_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER)
    resp = await client.post("/api/v1/auth/register", json={**REGISTER, "email": "owner@shop.com"})
    assert resp.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/register", json={**REGISTER, "password": "short"})
    assert resp.status_code == 422


async def test_login(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER)
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "owner@shop.com", "password": "strongpass1"}
    )
    assert ok.status_code == 200
    bad = await client.post(
        "/api/v1/auth/login", json={"email": "owner@shop.com", "password": "wrongpass1"}
    )
    assert bad.status_code == 401
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@shop.com", "password": "strongpass1"}
    )
    assert unknown.status_code == 401


async def test_refresh_flow(client: AsyncClient) -> None:
    tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    # An access token must not be accepted as a refresh token, and vice versa.
    wrong = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert wrong.status_code == 401
    me = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert me.status_code == 401


async def test_protected_routes_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401
    garbage = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/api/v1/shop", headers=garbage)).status_code == 401


async def test_token_for_deleted_user_rejected(client: AsyncClient) -> None:
    import uuid

    token = create_token(uuid.uuid4(), "access")
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_secret_encryption_roundtrip() -> None:
    encrypted = encrypt_secret("IGAAtoken123")
    assert encrypted != "IGAAtoken123"
    assert decrypt_secret(encrypted) == "IGAAtoken123"
