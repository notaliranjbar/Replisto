"""Alerts to the shop owner outside the panel.

The bot calls a `Notifier` when a customer is waiting for a person and when the wallet runs
low or empty. The panel already shows all of this (with browser notifications), so the
default notifier does nothing; another channel (email, push) can implement the protocol.
"""

from typing import Protocol

from app.models import Conversation, Shop


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
