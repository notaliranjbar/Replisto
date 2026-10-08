"""Manage a shop's wallet by hand (support credit, refunds, corrections).

    uv run python -m scripts.wallet show owner@shop.com
    uv run python -m scripts.wallet credit owner@shop.com 20.00 "Support credit"
    uv run python -m scripts.wallet debit owner@shop.com 5 "Correction"

Amounts are in US dollars. Every change is written to the wallet history the owner sees.
"""

import asyncio
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Shop, User, WalletEntry, WalletEntryKind
from app.services import billing


def _cents(dollars: str) -> int:
    try:
        return int((Decimal(dollars) * 100).to_integral_value())
    except InvalidOperation:
        raise SystemExit(f"not an amount: {dollars}") from None


async def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in ("show", "credit", "debit"):
        raise SystemExit(__doc__)
    action, email = argv[0], argv[1].strip().lower()
    async with SessionLocal() as db:
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Arabic text on the Windows console
    asyncio.run(main(sys.argv[1:]))
