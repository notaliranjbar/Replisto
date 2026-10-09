"""Product posts: reading the shop's Instagram posts, and linking each product to a post.

The bot shares a post when it recommends a product ("here's the post"), so the customer sees
the photos right in the chat. On Instagram a product's post is the one the owner put in the
product sheet (post_url column), otherwise the newest post whose caption names the product or
its code.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.core.text import normalize
from app.core.timeutil import utcnow
from app.models import Channel, InstagramAccount, InstagramPost, Product
from app.services.instagram import InstagramClient

logger = logging.getLogger(__name__)

# How a shared post is recorded in the conversation (panel and the bot's own history).
POST_MARKER = "[post]"
MAX_POSTS_PER_REPLY = 3

_PERMALINK = re.compile(r"instagram\.com/(?:[\w.]+/)?(p|reel|tv)/([\w-]+)", re.IGNORECASE)
_IMAGE_LINK = re.compile(r"img:(\S+)")


@dataclass(frozen=True)
class PostLink:
    """Something the bot can send after its message so the customer sees the product."""

    # Instagram: None when the owner linked a post we haven't read; sent as a plain link.
    media_id: str | None
    # How the post is recorded in the conversation: the Instagram link, or "img:<url>" for a
    # product photo.
    permalink: str
    caption: str = ""
    preview_url: str | None = None


def post_key(url: str) -> str | None:
    """Stable identity of a post link ("p/ABC123"), whatever the domain, path or query."""
    match = _PERMALINK.search(url or "")
    if match:
        return f"{match.group(1).lower()}/{match.group(2)}"
    match = _IMAGE_LINK.search(url or "")
    return f"img/{match.group(1)}" if match else None


def shared_post_keys(texts: list[str]) -> set[str]:
    """Posts already sent in a conversation, from its message texts."""
    return {key for text in texts for key in [post_key(text)] if key}


async def sync_posts(
    db: AsyncSession, account: InstagramAccount, instagram: InstagramClient
) -> int:
    """Replace the shop's stored posts with what Instagram has now."""
    if get_settings().instagram_dry_run:
        return 0  # nothing to read; keep the posts we have (the demo shop's)
    media = await instagram.list_media(decrypt_secret(account.access_token_encrypted))
    await db.execute(delete(InstagramPost).where(InstagramPost.shop_id == account.shop_id))
    for item in media:
        if not item.get("id") or not item.get("permalink"):
            continue
        db.add(
            InstagramPost(
                shop_id=account.shop_id,
                ig_media_id=str(item["id"]),
                permalink=item["permalink"],
                caption=(item.get("caption") or "")[:5000],
                media_type=str(item.get("media_type") or ""),
                preview_url=item.get("thumbnail_url") or item.get("media_url"),
                posted_at=_parse_time(item.get("timestamp")),
            )
        )
    account.posts_synced_at = utcnow()
    await db.commit()
    return len(media)


async def load_posts(db: AsyncSession, shop_id: uuid.UUID) -> list[InstagramPost]:
    return list(
        (await db.scalars(select(InstagramPost).where(InstagramPost.shop_id == shop_id))).all()
    )


def link_products(products: list[Product], posts: list[InstagramPost]) -> dict[str, PostLink]:
    """Map each product name to its post, if it has one."""
    by_key = {post_key(p.permalink): p for p in posts}
    newest_first = sorted(
        posts, key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True
    )
    captions = [(p, normalize(p.caption)) for p in newest_first]

    links: dict[str, PostLink] = {}
    for product in products:
        name = product.name.strip()
        if name in links:
            continue
        # 1. The owner's explicit link wins.
        if product.post_url:
            post = by_key.get(post_key(product.post_url))
            links[name] = _link(post) if post else PostLink(None, product.post_url)
            continue
        # 2. Otherwise the newest post whose caption names the product (or its code).
        wanted = normalize(name)
        sku = (product.sku or "").strip().lower()
        for post, caption in captions:
            if (len(wanted) >= 3 and wanted in caption) or (
                sku and re.search(rf"(?<![\w-]){re.escape(sku)}(?![\w-])", caption)
            ):
                links[name] = _link(post)
                break
    return links


def _link(post: InstagramPost) -> PostLink:
    return PostLink(post.ig_media_id, post.permalink, post.caption, post.preview_url)


async def shareable_posts(
    db: AsyncSession, shop_id: uuid.UUID, channel: Channel, products: list[Product]
) -> dict[str, PostLink]:
    """Map each product name to what the bot can show of it on this channel."""
    # Only the account's own posts render as cards in Instagram DMs.
    return link_products(products, await load_posts(db, shop_id))


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # Instagram sends "2026-09-20T10:15:30+0000"
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
