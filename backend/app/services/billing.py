"""The shop wallet: pay-as-you-go usage.

A shop tops up its wallet; every AI answer is deducted from it by the tokens it used (with a
minimum per answer). When the balance runs out the bot stops answering (the customer gets the shop's fallback message and
the conversation goes to the owner) until the owner tops up.

All amounts are integer rials. Every change is a row in the ledger (`WalletEntry`).
"""

import logging
import math
from datetime import timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import as_utc, utcnow
from app.models import Shop, WalletEntry, WalletEntryKind

logger = logging.getLogger(__name__)

# Don't remind about an empty wallet more often than this.
EMPTY_WALLET_REMINDER = timedelta(hours=12)


def enabled() -> bool:
    return get_settings().billing_enabled


def usage_cost(prompt_tokens: int, completion_tokens: int) -> int:
    settings = get_settings()
    cost = (
        prompt_tokens * settings.usage_rial_per_1k_prompt_tokens
        + completion_tokens * settings.usage_rial_per_1k_completion_tokens
    ) / 1000
    return max(math.ceil(cost), settings.usage_min_rial_per_reply)


def can_spend(shop: Shop) -> bool:
    return not enabled() or shop.balance_rial > 0


async def apply(
    db: AsyncSession,
    shop: Shop,
    amount_rial: int,
    kind: WalletEntryKind,
    description: str,
    details: dict[str, Any] | None = None,
) -> int:
    """Change the balance by `amount_rial` (negative spends) atomically; returns the new one.

    Commits. The UPDATE is done in SQL so two concurrent answers can't lose a deduction.
    """
    new_balance = await db.scalar(
        update(Shop)
        .where(Shop.id == shop.id)
        .values(balance_rial=Shop.balance_rial + amount_rial)
        .returning(Shop.balance_rial)
        .execution_options(synchronize_session=False)
    )
    assert new_balance is not None
    shop.balance_rial = new_balance
    db.add(
        WalletEntry(
            shop_id=shop.id,
            kind=kind,
            amount_rial=amount_rial,
            balance_after_rial=new_balance,
            description=description[:255],
            details=details or {},
        )
    )
    if amount_rial > 0 and new_balance >= get_settings().low_balance_rial:
        # Topped up: warn again next time it runs low.
        shop.low_balance_notified_at = None
        shop.empty_wallet_notified_at = None
    await db.commit()
    return new_balance


async def charge_usage(
    db: AsyncSession,
    shop: Shop,
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    description: str,
    details: dict[str, Any] | None = None,
) -> bool:
    """Deduct one AI answer. Returns True when the owner should now be told the balance is low."""
    if not enabled() or not (prompt_tokens or completion_tokens):
        return False
    prompt, completion = prompt_tokens or 0, completion_tokens or 0
    cost = usage_cost(prompt, completion)
    balance = await apply(
        db,
        shop,
        -cost,
        WalletEntryKind.USAGE,
        description,
        {"prompt_tokens": prompt, "completion_tokens": completion, **(details or {})},
    )
    return await _crossed_low_balance(db, shop, balance)


async def _crossed_low_balance(db: AsyncSession, shop: Shop, balance: int) -> bool:
    if balance >= get_settings().low_balance_rial or shop.low_balance_notified_at is not None:
        return False
    shop.low_balance_notified_at = utcnow()
    await db.commit()
    return True


async def should_remind_empty(db: AsyncSession, shop: Shop) -> bool:
    """True (and recorded) if the owner hasn't been told about the empty wallet recently."""
    last = shop.empty_wallet_notified_at
    if last is not None and utcnow() - as_utc(last) < EMPTY_WALLET_REMINDER:
        return False
    shop.empty_wallet_notified_at = utcnow()
    await db.commit()
    return True


def toman(rial: int) -> str:
    """Rial amount as a Persian-friendly toman string: "۱۲٬۵۰۰ تومان"."""
    return f"{rial // 10:,} تومان".replace(",", "٬")
