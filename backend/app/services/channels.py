"""The channel layer: how a reply reaches a customer on each messaging channel.

The bot (responder, products, handoffs, billing) doesn't know about channels. A conversation
records its channel and endpoint (`Conversation.channel` / `channel_ref`); `sender_for` turns
that into a `ChannelSender` that can send text and product posts there.

    Instagram account ──► Conversation ──► InstagramSender (Graph API)

A new channel adds its own sender here and a branch in `sender_for`.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import Channel, Conversation, InstagramAccount, Shop
from app.services import instagram as ig
from app.services.instagram import InstagramClient, InstagramError
from app.services.posts import PostLink

logger = logging.getLogger(__name__)

# Instagram only allows replies within 24h of the customer's last message. Keep a margin so a
# slow job doesn't hit the boundary.
_REPLY_WINDOW = timedelta(hours=24) - timedelta(minutes=5)


class SendError(Exception):
    """A channel refused or failed a send, in channel-independent terms."""

    def __init__(
        self, original: Exception, *, retryable: bool, endpoint_dead: bool = False
    ) -> None:
        super().__init__(str(original))
        # The channel's own error (e.g. InstagramError); re-raised for retries so
        # the worker's retry policy sees the real cause.
        self.original = original
        self.retryable = retryable
        # The account no longer works (token revoked, app removed); it has
        # been deactivated and the owner must reconnect it.
        self.endpoint_dead = endpoint_dead


class ChannelSender(Protocol):
    channel: Channel
    # Replies are only allowed this long after the customer's last message (None: always).
    reply_window: timedelta | None
    max_text_length: int

    async def send_text(self, text: str) -> str:
        """Send one chunk (already split to max_text_length); returns the external id."""
        ...

    async def send_post(self, post: PostLink) -> str: ...

    async def typing(self) -> None: ...


@dataclass
class Gateways:
    """API clients for the channels; a missing one means that channel can't send."""

    instagram: InstagramClient | None = None


class InstagramSender:
    channel = Channel.INSTAGRAM
    reply_window: timedelta | None = _REPLY_WINDOW
    max_text_length = ig.MAX_TEXT_LENGTH

    def __init__(
        self, db: AsyncSession, account: InstagramAccount, client: InstagramClient, customer: str
    ) -> None:
        self._db = db
        self._account = account
        self._client = client
        self._customer = customer
        self._token = decrypt_secret(account.access_token_encrypted)

    async def send_text(self, text: str) -> str:
        try:
            return await self._client.send_text(self._token, self._customer, text)
        except InstagramError as exc:
            raise await self._error(exc) from exc

    async def send_post(self, post: PostLink) -> str:
        try:
            if post.media_id:
                try:
                    return await self._client.send_post(self._token, self._customer, post.media_id)
                except InstagramError as exc:
                    if exc.token_invalid:
                        raise
                    # e.g. the post was deleted after our last sync: the link still helps.
            return await self._client.send_text(self._token, self._customer, post.permalink)
        except InstagramError as exc:
            raise await self._error(exc) from exc

    async def typing(self) -> None:
        return None

    async def _error(self, exc: InstagramError) -> SendError:
        if exc.token_invalid:
            self._account.is_active = False
            await self._db.commit()
            logger.warning("instagram token revoked for shop %s", self._account.shop_id)
        return SendError(exc, retryable=exc.retryable, endpoint_dead=exc.token_invalid)


async def sender_for(
    db: AsyncSession, shop: Shop, conversation: Conversation, gateways: Gateways
) -> ChannelSender | None:
    """The sender for this conversation, or None if its endpoint can't be used right now
    (disconnected, deactivated or channel switched off)."""
    if conversation.channel == Channel.INSTAGRAM:
        if not get_settings().instagram_enabled or gateways.instagram is None:
            return None
        account = await db.scalar(
            select(InstagramAccount).where(InstagramAccount.shop_id == shop.id)
        )
        if account is None or not account.is_active:
            return None
        return InstagramSender(db, account, gateways.instagram, conversation.customer_id)

    return None


def split_text(text: str, limit: int) -> list[str]:
    return ig.split_text(text, limit)
