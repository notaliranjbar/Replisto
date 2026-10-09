import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.deps import JobQueue
from app.core.config import get_settings
from app.services.webhook import parse_comment_events, parse_messaging_events, verify_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)


@router.get("/instagram")
async def verify_subscription(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta calls this once when the webhook URL is saved in the App Dashboard."""
    expected = get_settings().meta_webhook_verify_token
    if mode != "subscribe" or not expected or verify_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return PlainTextResponse(challenge)


@router.post("/instagram")
async def receive(request: Request, queue: JobQueue) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(body, signature, get_settings().meta_app_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid signature")
    payload = _json_object(body)
    if not get_settings().instagram_enabled:
        return {"status": "ignored"}  # Instagram is switched off; acknowledge so Meta stops

    # Only enqueue here: Meta disables webhooks that answer slowly.
    for event in parse_messaging_events(payload):
        await queue.enqueue("process_event", event, job_id=f"event:{event.mid}")
    for comment in parse_comment_events(payload):
        await queue.enqueue("process_comment", comment, job_id=f"comment:{comment.comment_id}")
    return {"status": "ok"}


def _json_object(body: bytes) -> dict:
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid json") from None
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid payload")
    return payload
