import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.api.deps import DbSession, JobQueue
from app.core.config import get_settings
from app.models import InstagramAccount
from app.services.webhook import parse_comment_events, parse_messaging_events, verify_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)


async def _forward_to_javab(body: bytes, signature: str | None) -> None:
    base = get_settings().javab_backend_url.rstrip("/")
    if not base:
        return
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{base}/api/v1/webhooks/instagram", content=body, headers=headers)
    except Exception:
        logger.exception("Failed to forward Instagram webhook to Javab")


@router.get("/instagram")
async def verify_subscription(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    expected = get_settings().meta_webhook_verify_token
    if mode != "subscribe" or not expected or verify_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return PlainTextResponse(challenge)


@router.post("/instagram")
async def receive(request: Request, queue: JobQueue, db: DbSession) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(body, signature, get_settings().meta_app_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid signature")
    payload = _json_object(body)
    if not get_settings().instagram_enabled:
        return {"status": "ignored"}

    entries = payload.get("entry")
    entry_ids = {
        str(e.get("id"))
        for e in (entries if isinstance(entries, list) else [])
        if isinstance(e, dict) and e.get("id")
    }

    local_ig_ids: set[str] = set()
    if entry_ids:
        rows = (
            await db.scalars(
                select(InstagramAccount.ig_user_id).where(InstagramAccount.ig_user_id.in_(entry_ids))
            )
        ).all()
        local_ig_ids = set(rows)

    if entry_ids - local_ig_ids:
        asyncio.create_task(_forward_to_javab(body, signature))

    if not local_ig_ids:
        return {"status": "ok"}

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
