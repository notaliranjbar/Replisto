"""Alerts to the shop owner outside the panel.

The bot calls a `Notifier` when a customer is waiting for a person and when the wallet runs
low or empty. The panel shows all of this too (with browser notifications), but only while
it's open, so `EmailNotifier` also emails the owner (EMAIL_ALERTS), in their language.
"""

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.i18n import tr
from app.models import Conversation, Shop, User
from app.services import billing
from app.services.email import action_email, send_email

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    async def handoff(self, shop: Shop, conversation: Conversation) -> None: ...

    async def wallet_low(self, shop: Shop) -> None: ...

    async def wallet_empty(self, shop: Shop) -> None: ...


class NullNotifier:
    async def handoff(self, shop: Shop, conversation: Conversation) -> None:
        return None

    async def wallet_low(self, shop: Shop) -> None:
        return None

    async def wallet_empty(self, shop: Shop) -> None:
        return None


class EmailNotifier:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def handoff(self, shop: Shop, conversation: Conversation) -> None:
        who = conversation.customer_name or (
            f"@{conversation.customer_username}" if conversation.customer_username else ""
        )
        lang = shop.language
        await self._send(
            shop,
            tr("A customer is waiting for you", lang),
            tr(
                "{customer} asked something the assistant couldn't answer. Reply from your panel:",
                lang,
                customer=who or tr("A customer", lang),
            ),
            tr("Open the conversation", lang),
            f"/inbox/{conversation.id}",
            quote=(conversation.handoff_question or "")[:1500],
        )

    async def wallet_low(self, shop: Shop) -> None:
        lang = shop.language
        await self._send(
            shop,
            tr("Your Replisto wallet is running low", lang),
            tr(
                "Your balance is {balance}. Top it up so the assistant keeps answering your customers.",
                lang,
                balance=billing.usd(shop.balance_cents),
            ),
            tr("Top up", lang),
            "/billing",
        )

    async def wallet_empty(self, shop: Shop) -> None:
        lang = shop.language
        await self._send(
            shop,
            tr("Your Replisto wallet is empty", lang),
            tr(
                "The assistant has stopped answering customers and is passing their messages to you. Top up to turn it back on.",
                lang,
            ),
            tr("Top up", lang),
            "/billing",
        )

    async def _send(
        self, shop: Shop, title: str, intro: str, button: str, path: str, quote: str = ""
    ) -> None:
        settings = get_settings()
        if not settings.email_alerts:
            return
        owner = await self._db.get(User, shop.owner_id)
        if owner is None or not owner.is_active:
            return
        text, page = action_email(
            title=title,
            intro=intro,
            button=button,
            link=f"{settings.frontend_url.rstrip('/')}{path}",
            note=tr(
                "You get these emails because you run {shop} on Replisto.",
                shop.language,
                shop=shop.name,
            ),
            quote=quote,
            rtl=shop.language == "ar",
        )
        try:
            await send_email(owner.email, title, text, page)
        except Exception:
            logger.exception("could not email shop %s", shop.id)
