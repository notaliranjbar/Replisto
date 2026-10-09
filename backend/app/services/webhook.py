"""Parsing and verification of Instagram webhooks: messages (DMs, story replies and
mentions) and comments on the account's posts and reels."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def verify_signature(body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Check Meta's `X-Hub-Signature-256: sha256=<hex>` HMAC of the raw request body."""
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@dataclass(frozen=True)
class MessagingEvent:
    account_ig_id: str  # the shop's Instagram account (webhook entry.id)
    customer_igsid: str  # the other side of the conversation
    mid: str
    text: str
    # True when the message was sent *by* the shop's account (by the owner or by us).
    is_echo: bool
    timestamp: datetime
    attachment_types: tuple[str, ...] = ()
    # A reply to one of the shop's stories: which one (its media id).
    story_id: str | None = None

    @property
    def display_text(self) -> str:
        """Text as stored in history; non-text content becomes a marker like `[image]`."""
        markers = " ".join(f"[{t}]" for t in self.attachment_types)
        return " ".join(p for p in (self.text, markers) if p)


def parse_messaging_events(payload: dict[str, Any]) -> list[MessagingEvent]:
    """Extract message events; reactions, reads, deletions and unsupported types are dropped."""
    if payload.get("object") != "instagram":
        return []
    events: list[MessagingEvent] = []
    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id", ""))
        for item in entry.get("messaging") or []:
            message = item.get("message")
            if not isinstance(message, dict) or not message.get("mid"):
                continue
            if message.get("is_deleted") or message.get("is_unsupported"):
                continue
            is_echo = bool(message.get("is_echo"))
            party = item.get("recipient") if is_echo else item.get("sender")
            customer_id = str((party or {}).get("id", ""))
            if not account_id or not customer_id or customer_id == account_id:
                continue
            timestamp_ms = item.get("timestamp")
            timestamp = (
                datetime.fromtimestamp(timestamp_ms / 1000, UTC)
                if isinstance(timestamp_ms, int | float)
                else datetime.now(UTC)
            )
            story = (message.get("reply_to") or {}).get("story") or {}
            events.append(
                MessagingEvent(
                    account_ig_id=account_id,
                    customer_igsid=customer_id,
                    mid=message["mid"],
                    text=message.get("text") or "",
                    is_echo=is_echo,
                    timestamp=timestamp,
                    attachment_types=tuple(
                        str(a.get("type", "attachment")) for a in message.get("attachments") or []
                    )
                    + (("story_reply",) if story else ()),
                    story_id=str(story["id"]) if story.get("id") else None,
                )
            )
    return events


@dataclass(frozen=True)
class CommentEvent:
    account_ig_id: str  # the shop's Instagram account (webhook entry.id)
    comment_id: str
    text: str
    author_id: str
    author_username: str
    media_id: str
    media_product_type: str
    timestamp: datetime
    # Set when the comment replies to another comment.
    parent_id: str | None = None


def parse_comment_events(payload: dict[str, Any]) -> list[CommentEvent]:
    """New comments on the account's posts and reels. The account's own comments (its replies)
    are dropped, so the bot never answers itself."""
    if payload.get("object") != "instagram":
        return []
    events: list[CommentEvent] = []
    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id", ""))
        seconds = entry.get("time")
        timestamp = (
            datetime.fromtimestamp(seconds, UTC)
            if isinstance(seconds, int | float)
            else datetime.now(UTC)
        )
        for change in entry.get("changes") or []:
            if change.get("field") != "comments":
                continue
            value = change.get("value") or {}
            author = value.get("from") or {}
            media = value.get("media") or {}
            comment_id, author_id = str(value.get("id") or ""), str(author.get("id") or "")
            if not account_id or not comment_id or not author_id or author_id == account_id:
                continue
            events.append(
                CommentEvent(
                    account_ig_id=account_id,
                    comment_id=comment_id,
                    text=str(value.get("text") or ""),
                    author_id=author_id,
                    author_username=str(author.get("username") or ""),
                    media_id=str(media.get("id") or ""),
                    media_product_type=str(media.get("media_product_type") or ""),
                    timestamp=timestamp,
                    parent_id=str(value["parent_id"]) if value.get("parent_id") else None,
                )
            )
    return events
