import os

# Must be set before app modules read settings. Ignore any local backend/.env so tests always
# run against these values only.
os.environ["APP_ENV_FILE"] = ""
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-123456"
os.environ["ENCRYPTION_KEY"] = "u5Q3pX0cQyJ6c1l0vH1i8wK3rP4mZ2nB7eT9aY6dF0g="
os.environ["META_APP_ID"] = "ig-app-id"
os.environ["META_APP_SECRET"] = "ig-app-secret"
os.environ["META_WEBHOOK_VERIFY_TOKEN"] = "verify-me"
os.environ["PUBLIC_BASE_URL"] = "https://api.test"
os.environ["FRONTEND_URL"] = "https://panel.test"
os.environ["LLM_BASE_URL"] = "https://llm.test/v1"
os.environ["LLM_MODEL"] = "test-model"
os.environ["INSTAGRAM_ENABLED"] = "true"
# Wallet charging is covered by its own tests (which switch it on).
os.environ["BILLING_ENABLED"] = "false"
os.environ["ZARINPAL_SANDBOX"] = "true"
os.environ["ABAN_API_BASE"] = "https://aban.test"

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_http, get_instagram_client, get_queue
from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.services.instagram import InstagramClient


@dataclass
class QueuedJob:
    function: str
    args: tuple[Any, ...]
    job_id: str | None
    defer_seconds: float


class RecordingQueue:
    def __init__(self) -> None:
        self.jobs: list[QueuedJob] = []

    async def enqueue(
        self, function: str, *args: Any, job_id: str | None = None, defer_seconds: float = 0
    ) -> None:
        self.jobs.append(QueuedJob(function, args, job_id, defer_seconds))


@dataclass
class FakeMeta:
    """Stands in for Meta's servers behind a real InstagramClient (via httpx.MockTransport)."""

    ig_user_id: str = "17841400000000001"
    username: str = "mahsa.boutique"
    sent: list[dict[str, Any]] = field(default_factory=list)
    subscribed: bool = False
    # When set, the send endpoint answers with this (status, body) instead of succeeding.
    send_error: tuple[int, dict[str, Any]] | None = None
    refresh_error: tuple[int, dict[str, Any]] | None = None
    # Posts returned by /me/media, served two per page to exercise pagination.
    media: list[dict[str, Any]] = field(default_factory=list)
    # When set, sharing a post (MEDIA_SHARE) fails with this; plain text still works.
    post_error: tuple[int, dict[str, Any]] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "api.instagram.com" and path == "/oauth/access_token":
            form = parse_qs(request.content.decode())
            if form["code"][0] == "bad-code":
                return httpx.Response(
                    400,
                    json={"error_type": "OAuthException", "code": 400, "error_message": "bad"},
                )
            return httpx.Response(200, json={"data": [{"access_token": "short-token"}]})
        if path == "/access_token":
            return httpx.Response(200, json={"access_token": "long-token", "expires_in": 5184000})
        if path == "/refresh_access_token":
            if self.refresh_error:
                return httpx.Response(self.refresh_error[0], json=self.refresh_error[1])
            return httpx.Response(
                200, json={"access_token": "refreshed-token", "expires_in": 5184000}
            )
        if path.endswith("/me/subscribed_apps"):
            self.subscribed = True
            return httpx.Response(200, json={"success": True})
        if path.endswith("/me/media"):
            start = int(request.url.params.get("after", 0))
            page: dict[str, Any] = {"data": self.media[start : start + 2]}
            if start + 2 < len(self.media):
                page["paging"] = {
                    "next": f"https://graph.instagram.com/v23.0/me/media?after={start + 2}"
                }
            return httpx.Response(200, json=page)
        if path.endswith("/me/messages"):
            if self.send_error:
                return httpx.Response(self.send_error[0], json=self.send_error[1])
            body = json.loads(request.content)
            if self.post_error and "attachment" in body["message"]:
                return httpx.Response(self.post_error[0], json=self.post_error[1])
            body["token"] = request.headers["Authorization"].removeprefix("Bearer ")
            self.sent.append(body)
            return httpx.Response(
                200,
                json={
                    "recipient_id": body["recipient"]["id"],
                    "message_id": f"bot-mid-{len(self.sent)}",
                },
            )
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": self.ig_user_id, "username": self.username})
        return httpx.Response(404, json={"error": {"message": f"unexpected {path}", "code": 100}})

    def client(self) -> InstagramClient:
        return InstagramClient(httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))


@dataclass
class FakeZarinpal:
    """Zarinpal's sandbox payment API."""

    requests: list[dict[str, Any]] = field(default_factory=list)
    verifies: list[dict[str, Any]] = field(default_factory=list)
    verify_code: int = 100

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/request.json"):
            self.requests.append(body)
            return httpx.Response(
                200, json={"data": {"code": 100, "authority": f"A{len(self.requests):035d}"}}
            )
        self.verifies.append(body)
        if self.verify_code not in (100, 101):
            return httpx.Response(200, json={"data": [], "errors": {"code": self.verify_code}})
        return httpx.Response(
            200,
            json={"data": {"code": self.verify_code, "ref_id": 201, "card_pan": "6037****1234"}},
        )


@dataclass
class FakeAban:
    """Aban Gateway's invoice API (card-to-card with automatic confirmation)."""

    invoices: dict[str, dict[str, Any]] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)
    verifies: list[str] = field(default_factory=list)
    # When set, creating an invoice fails with this (status, error code).
    create_error: tuple[int, str] | None = None

    def pay(self, invoice_id: str) -> None:
        """The owner transferred the exact amount and the bank SMS arrived."""
        self.invoices[invoice_id]["status"] = "paid"

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != "Bearer ag_test_token":
            return httpx.Response(401, json={"detail": "bad token"})
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/invoices":
            if self.create_error:
                status, code = self.create_error
                return httpx.Response(status, json={"error": {"code": code, "message": code}})
            body = json.loads(request.content)
            self.created.append(body)
            invoice_id = f"inv_{len(self.created):020d}"
            invoice = {
                "invoice_id": invoice_id,
                "status": "pending",
                "amount_rial": body["amount_rial"],
                "payable_rial": body["amount_rial"] + 3240,
                "order_id": body.get("order_id"),
                "payment_url": f"https://abangateway.ir/pay/{invoice_id}",
                "verified": False,
            }
            self.invoices[invoice_id] = invoice
            return httpx.Response(201, json=invoice)
        parts = path.split("/")  # ['', 'api', 'v1', 'invoices', id, action?]
        invoice = self.invoices.get(parts[4]) if len(parts) > 4 else None
        if invoice is None:
            return httpx.Response(404, json={"error": {"code": "invoice_not_found"}})
        if request.method == "GET":
            return httpx.Response(200, json=invoice)
        if parts[-1] == "verify":
            self.verifies.append(invoice["invoice_id"])
            if invoice["status"] != "paid":
                return httpx.Response(402, json={"error": {"code": "not_yet_paid"}})
            if invoice["verified"]:
                return httpx.Response(409, json={"error": {"code": "already_verified"}})
            invoice["verified"] = True
            return httpx.Response(200, json={"verified": True, **invoice})
        return httpx.Response(404, json={"error": {"code": "invalid_request"}})


class FakeWeb:
    """Google Sheets/Drive downloads, an OpenAI-compatible LLM and the payment gateways, behind
    httpx.MockTransport.

    - `files[url] = (status, body, content_type)` serves a Google download URL.
    - `llm_replies` is a queue of assistant messages the fake LLM returns in order.
    """

    def __init__(self) -> None:
        self.zarinpal = FakeZarinpal()
        self.aban = FakeAban()
        self.files: dict[str, tuple[int, bytes, str]] = {}
        self.llm_replies: list[dict[str, Any]] = []
        self.llm_requests: list[dict[str, Any]] = []
        self.llm_status = 200
        # Parameters the fake model refuses, like newer OpenAI models do with max_tokens.
        self.llm_rejects: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "sandbox.zarinpal.com":
            return self.zarinpal.handler(request)
        if request.url.host == "aban.test":
            return self.aban.handler(request)
        if request.url.host == "llm.test":
            body = json.loads(request.content)
            self.llm_requests.append(body)
            for param in self.llm_rejects & body.keys():
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": f"Unsupported parameter: '{param}' is not supported "
                            "with this model.",
                            "type": "invalid_request_error",
                            "param": param,
                        }
                    },
                )
            if self.llm_status != 200:
                return httpx.Response(self.llm_status, json={"error": "busy"})
            message = self.llm_replies.pop(0) if self.llm_replies else {"content": "باشه"}
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", **message}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                },
            )
        served = self.files.get(str(request.url))
        if served is None:
            return httpx.Response(404, text="not found", headers={"content-type": "text/html"})
        status, content, content_type = served
        return httpx.Response(status, content=content, headers={"content-type": content_type})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    @staticmethod
    def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


@pytest.fixture
def fake_web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the server has an AI provider key."""
    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key")


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        yield session


@pytest.fixture
def fake_meta() -> FakeMeta:
    return FakeMeta()


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession],
    fake_meta: FakeMeta,
    fake_web: FakeWeb,
    queue: RecordingQueue,
) -> AsyncIterator[AsyncClient]:
    async def _get_db() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_instagram_client] = fake_meta.client
    app.dependency_overrides[get_http] = fake_web.client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@shop.ir", "password": "strongpass1", "shop_name": "Mahsa Shop"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    """Rate limits live in memory; every test starts with none used."""
    from app.api.routes import account, auth

    auth.configure_login_throttle()
    for throttle in (
        auth._verify_email_minute,
        auth._verify_email_day,
        account._sms_per_user,
        account._sms_per_phone,
        account._sms_per_user_day,
    ):
        throttle.clear()
    auth._last_reset_request.clear()


@pytest.fixture(autouse=True)
def _email_check_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests use a fresh, unverified sign-up; test_verification covers the closed panel."""
    monkeypatch.setattr(get_settings(), "require_verified_email", False)


@pytest.fixture
def billing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Charge AI answers to the shop's wallet, as in production."""
    monkeypatch.setattr(get_settings(), "billing_enabled", True)
