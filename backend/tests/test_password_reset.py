import pytest
from httpx import AsyncClient

from app.api.routes import auth

API = "/api/v1/auth/password"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    sent: list[tuple[str, str, str]] = []

    async def fake_send(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        sent.append((to, subject, body))

    monkeypatch.setattr(auth, "send_email", fake_send)
    auth._last_reset_request.clear()
    return sent


def _token(body: str) -> str:
    return body.split("token=", 1)[1].split()[0]


async def test_reset_flow(client: AsyncClient, auth_headers: dict, outbox: list) -> None:
    resp = await client.post(f"{API}/forgot", json={"email": " Owner@Shop.com "})
    assert resp.status_code == 202
    [(to, _, body)] = outbox
    assert to == "owner@shop.com" and "https://panel.test/reset-password?token=" in body

    token = _token(body)
    resp = await client.post(f"{API}/reset", json={"token": token, "new_password": "newpass123"})
    assert resp.status_code == 204
    login = await client.post(
        "/api/v1/auth/login", json={"email": "owner@shop.com", "password": "newpass123"}
    )
    assert login.status_code == 200

    # The link works once: the password it was made for is gone.
    resp = await client.post(f"{API}/reset", json={"token": token, "new_password": "another12"})
    assert resp.status_code == 400


async def test_unknown_email_looks_the_same(client: AsyncClient, outbox: list) -> None:
    resp = await client.post(f"{API}/forgot", json={"email": "nobody@shop.com"})
    assert resp.status_code == 202 and outbox == []


async def test_requests_are_throttled(
    client: AsyncClient, auth_headers: dict, outbox: list
) -> None:
    await client.post(f"{API}/forgot", json={"email": "owner@shop.com"})
    await client.post(f"{API}/forgot", json={"email": "owner@shop.com"})
    assert len(outbox) == 1


async def test_garbage_token(client: AsyncClient) -> None:
    resp = await client.post(
        f"{API}/reset", json={"token": "not-a-real-token", "new_password": "newpass123"}
    )
    assert resp.status_code == 400
