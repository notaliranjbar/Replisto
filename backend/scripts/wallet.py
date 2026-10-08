"""Manage a shop's wallet by hand (support, card-to-card payments before the gateway works).

    uv run python -m scripts.wallet show owner@shop.ir
    uv run python -m scripts.wallet credit owner@shop.ir 200000 "کارت به کارت ۱۴۰۵/۰۷/۱۰"
    uv run python -m scripts.wallet debit owner@shop.ir 50000 "اصلاح"

Amounts are in toman. Every change is written to the wallet history the owner sees.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Shop, User, WalletEntry, WalletEntryKind
from app.services import billing


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
            toman = int(argv[2])
            note = argv[3] if len(argv) > 3 else "تنظیم دستی"
            amount = toman * 10 if action == "credit" else -toman * 10
            await billing.apply(db, shop, amount, WalletEntryKind.ADJUSTMENT, note)
        print(f"{shop.name}: {billing.toman(shop.balance_rial)}")
        entries = await db.scalars(
            select(WalletEntry)
            .where(WalletEntry.shop_id == shop.id)
            .order_by(WalletEntry.created_at.desc())
            .limit(10)
        )
        for entry in entries:
            print(
                f"  {entry.created_at:%Y-%m-%d %H:%M}  {entry.amount_rial // 10:>+12,}  "
                f"{entry.description}"
            )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Persian text on the Windows console
    asyncio.run(main(sys.argv[1:]))
