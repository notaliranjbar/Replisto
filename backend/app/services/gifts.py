"""The sign-up gift: free wallet credit, once per real person rather than once per email.

Signing up alone earns nothing (emails are free to make). The gift comes when the owner
verifies their mobile number. Each number can earn a gift once: it's remembered (hashed) in
`gift_claims`, even after the shop is deleted, so deleting and signing up again with the same
number doesn't pay twice.

`check` is called when a number is verified; it is idempotent.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import secret_digest
from app.core.timeutil import utcnow
from app.models import GiftClaim, Shop, User, WalletEntryKind
from app.services import billing

logger = logging.getLogger(__name__)


def _key(kind: str, value: str) -> str:
    return secret_digest(f"gift:{kind}:{value}")


def _phone_key(owner: User) -> str | None:
    return _key("phone", owner.phone) if owner.phone and owner.phone_verified_at else None


def amount() -> int:
    return get_settings().signup_credit_cents if billing.enabled() else 0


async def status(db: AsyncSession, shop: Shop) -> dict[str, bool | int]:
    """What the panel shows: the gift, and which steps are still missing."""
    owner = await db.get(User, shop.owner_id)
    assert owner is not None
    return {
        "amount_cents": amount(),
        "granted": shop.signup_gift_at is not None,
        "phone_verified": _phone_key(owner) is not None,
    }


async def check(db: AsyncSession, shop: Shop) -> int:
    """Give the gift if the shop just became eligible; returns the cents given (0 if not)."""
    owner = await db.get(User, shop.owner_id)
    if owner is None:
        return 0
    key = _phone_key(owner)
    if key is None:
        return 0
    claim = await db.scalar(select(GiftClaim).where(GiftClaim.key == key))

    if shop.signup_gift_at is not None:
        # Already gifted: this number can't earn another shop a gift either.
        if claim is None:
            db.add(GiftClaim(key=key, shop_id=shop.id))
            await _commit(db)
        return 0

    credit = amount()
    if credit <= 0:
        return 0
    if claim is not None and claim.shop_id != shop.id:
        return 0  # this number already got a gift for another shop

    if claim is None:
        db.add(GiftClaim(key=key, shop_id=shop.id))
    shop.signup_gift_at = utcnow()
    if not await _commit(db):
        return 0
    await billing.apply(db, shop, credit, WalletEntryKind.BONUS, "Welcome gift")
    logger.info("sign-up gift of %s cents given to shop %s", credit, shop.id)
    return credit


async def _commit(db: AsyncSession) -> bool:
    try:
        await db.commit()
    except IntegrityError:  # the same identity claimed concurrently
        await db.rollback()
        return False
    return True
