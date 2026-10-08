"""Manage wallets by hand: support credit, corrections, and Whish Money / OMT transfers.

    uv run python -m scripts.wallet show owner@shop.com
    uv run python -m scripts.wallet credit owner@shop.com 20.00 "Support credit"
    uv run python -m scripts.wallet debit owner@shop.com 5 "Correction"

    uv run python -m scripts.wallet pending                       # transfers to check
    uv run python -m scripts.wallet approve <payment-id>          # found it: credit the wallet
    uv run python -m scripts.wallet reject <payment-id> "Not received"

Amounts are in US dollars. Every change is written to the wallet history the owner sees.
"""

import asyncio
import sys
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Payment, PaymentStatus, Shop, User, WalletEntry, WalletEntryKind
from app.services import billing, payments


def _cents(dollars: str) -> int:
    try:
        return int((Decimal(dollars) * 100).to_integral_value())
    except InvalidOperation:
        raise SystemExit(f"not an amount: {dollars}") from None


async def _show(db, shop: Shop) -> None:  # type: ignore[no-untyped-def]
    print(f"{shop.name}: {billing.usd(shop.balance_cents)}")
    entries = await db.scalars(
        select(WalletEntry)
        .where(WalletEntry.shop_id == shop.id)
        .order_by(WalletEntry.created_at.desc())
        .limit(10)
    )
    for entry in entries:
        print(
            f"  {entry.created_at:%Y-%m-%d %H:%M}  {billing.usd(entry.amount_cents):>12}  "
            f"{entry.description}"
        )


async def _pending(db) -> None:  # type: ignore[no-untyped-def]
    rows = await db.execute(
        select(Payment, Shop, User)
        .join(Shop, Shop.id == Payment.shop_id)
        .join(User, User.id == Shop.owner_id)
        .where(
            Payment.gateway.in_(payments.MANUAL_METHODS),
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(Payment.created_at)
    )
    found = False
    for payment, shop, user in rows:
        found = True
        print(
            f"{payment.id}  {payment.created_at:%Y-%m-%d %H:%M}  {payment.gateway:<5}  "
            f"{billing.usd(payment.amount_cents):>10}  ref {payment.ref_id}  "
            f"{shop.name} <{user.email}>"
        )
    if not found:
        print("no transfers waiting")


async def _payment(db, raw_id: str) -> Payment:  # type: ignore[no-untyped-def]
    try:
        payment = await db.get(Payment, uuid.UUID(raw_id))
    except ValueError:
        payment = None
    if payment is None:
        raise SystemExit(f"no payment {raw_id}")
    return payment


async def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    action = argv[0]
    async with SessionLocal() as db:
        if action == "pending":
            await _pending(db)
            return
        if action in ("approve", "reject"):
            if len(argv) < 2:
                raise SystemExit(__doc__)
            payment = await _payment(db, argv[1])
            if action == "approve":
                done = await payments.approve_transfer(db, payment)
            else:
                reason = argv[2] if len(argv) > 2 else ""
                done = await payments.reject_transfer(db, payment, reason)
            if not done:
                raise SystemExit(f"payment {payment.id} isn't a transfer waiting to be checked")
            print(f"{action}d {payment.id}")
            return
        if action not in ("show", "credit", "debit") or len(argv) < 2:
            raise SystemExit(__doc__)
        email = argv[1].strip().lower()
        shop = await db.scalar(select(Shop).join(User).where(User.email == email))
        if shop is None:
            raise SystemExit(f"no shop for {email}")
        if action != "show":
            if len(argv) < 3:
                raise SystemExit(__doc__)
            cents = _cents(argv[2])
            note = argv[3] if len(argv) > 3 else "Manual adjustment"
            amount = cents if action == "credit" else -cents
            await billing.apply(db, shop, amount, WalletEntryKind.ADJUSTMENT, note)
        await _show(db, shop)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Arabic text on the Windows console
    asyncio.run(main(sys.argv[1:]))
