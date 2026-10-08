import hashlib
import hmac
import json
from typing import Any

from httpx import AsyncClient

from app.services.instagram import split_text
from app.services.webhook import parse_messaging_events, verify_signature
from tests.conftest import RecordingQueue

ACCOUNT = "17841400000000001"
CUSTOMER = "998877"


def _payload(*messaging: dict[str, Any]) -> dict[str, Any]:
    return {"object": "instagram", "entry": [{"id": ACCOUNT, "time": 1, "messaging": messaging}]}


def _incoming(mid: str, text: str = "Hi", ts: int = 1_790_000_000_000, **extra: Any):
    return {
        "sender": {"id": CUSTOMER},
        "recipient": {"id": ACCOUNT},
        "timestamp": ts,
        "message": {"mid": mid, "text": text, **extra},
    }


def _sign(body: bytes, secret: str = "ig-app-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_verify_subscription(client: AsyncClient) -> None:
    params = {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42abc"}
    resp = await client.get("/webhooks/instagram", params=params)
    assert resp.status_code == 200
    assert resp.text == "42abc"

    bad = await client.get("/webhooks/instagram", params={**params, "hub.verify_token": "nope"})
    assert bad.status_code == 403


async def test_receive_requires_valid_signature(client: AsyncClient, queue: RecordingQueue) -> None:
    body = json.dumps(_payload(_incoming("m1"))).encode()
    missing = await client.post("/webhooks/instagram", content=body)
    assert missing.status_code == 403
    forged = await client.post(
        "/webhooks/instagram",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body, "wrong-secret")},
    )
    assert forged.status_code == 403
    assert queue.jobs == []


async def test_receive_enqueues_events(client: AsyncClient, queue: RecordingQueue) -> None:
    body = json.dumps(_payload(_incoming("m1", "How much is this dress?"))).encode()
    resp = await client.post(
        "/webhooks/instagram", content=body, headers={"X-Hub-Signature-256": _sign(body)}
    )
    assert resp.status_code == 200
    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert job.function == "process_event"
    assert job.job_id == "event:m1"
    event = job.args[0]
    assert event.account_ig_id == ACCOUNT
    assert event.customer_igsid == CUSTOMER
    assert event.text == "How much is this dress?"


async def test_receive_rejects_invalid_json(client: AsyncClient) -> None:
    body = b"not json"
    resp = await client.post(
        "/webhooks/instagram", content=body, headers={"X-Hub-Signature-256": _sign(body)}
    )
    assert resp.status_code == 400


def test_parse_echo_uses_recipient_as_customer() -> None:
    echo = {
        "sender": {"id": ACCOUNT},
        "recipient": {"id": CUSTOMER},
        "timestamp": 1_790_000_000_000,
        "message": {"mid": "e1", "text": "Hi, it's in stock", "is_echo": True},
    }
    [event] = parse_messaging_events(_payload(echo))
    assert event.is_echo
    assert event.customer_igsid == CUSTOMER


def test_parse_attachments_and_skips() -> None:
    events = parse_messaging_events(
        _payload(
            _incoming("m1", "", attachments=[{"type": "image", "payload": {"url": "x"}}]),
            _incoming("m2", "deleted", is_deleted=True),
            _incoming("m3", "", is_unsupported=True),
            {"sender": {"id": CUSTOMER}, "recipient": {"id": ACCOUNT}, "read": {"mid": "m1"}},
            {"sender": {"id": CUSTOMER}, "recipient": {"id": ACCOUNT}, "reaction": {"mid": "m1"}},
        )
    )
    assert [e.mid for e in events] == ["m1"]
    assert events[0].display_text == "[image]"


def test_parse_ignores_other_objects() -> None:
    assert parse_messaging_events({"object": "page", "entry": []}) == []
    assert parse_messaging_events({}) == []


def test_verify_signature_edge_cases() -> None:
    body = b"{}"
    assert verify_signature(body, _sign(body), "ig-app-secret")
    assert not verify_signature(body, _sign(body), "")  # unconfigured secret rejects all
    assert not verify_signature(body, "md5=abc", "ig-app-secret")


def test_split_text() -> None:
    assert split_text("Short") == ["Short"]
    long = ("This is a fairly long sentence. " * 80).strip()
    chunks = split_text(long)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert " ".join(chunks).split() == long.split()  # nothing lost at the seams
