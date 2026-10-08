"""usd wallet and stripe

The wallet moves from rial to US cents and top-ups move to Stripe Checkout:
- balances, wallet history and payments are renamed to *_cents and converted at
  RIAL_PER_CENT (existing balances keep roughly their value);
- a payment's gateway id ("authority") becomes `session_id`, wide enough for Stripe's ids;
  the card number column goes (Stripe never shares it);
- shops get a `currency` for their product prices (USD by default), and prices keep cents.

Revision ID: 3f1c9a7d2b6e
Revises: 56c471d7558e
Create Date: 2026-10-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3f1c9a7d2b6e"
down_revision: Union[str, Sequence[str], None] = "56c471d7558e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The conversion rate for existing amounts (about 1,000,000 rial to the dollar).
RIAL_PER_CENT = 10_000


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.alter_column("balance_rial", new_column_name="balance_cents")
        batch_op.add_column(
            sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False)
        )
    op.execute(f"UPDATE shops SET balance_cents = balance_cents / {RIAL_PER_CENT}")

    with op.batch_alter_table("wallet_entries", schema=None) as batch_op:
        batch_op.alter_column("amount_rial", new_column_name="amount_cents")
        batch_op.alter_column("balance_after_rial", new_column_name="balance_after_cents")
    op.execute(
        "UPDATE wallet_entries SET "
        f"amount_cents = amount_cents / {RIAL_PER_CENT}, "
        f"balance_after_cents = balance_after_cents / {RIAL_PER_CENT}"
    )

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.alter_column("amount_rial", new_column_name="amount_cents")
        batch_op.drop_constraint(batch_op.f("uq_payments_authority"), type_="unique")
        batch_op.alter_column(
            "authority",
            new_column_name="session_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=255),
        )
        batch_op.alter_column(
            "ref_id", existing_type=sa.String(length=64), type_=sa.String(length=255)
        )
        batch_op.drop_column("card_pan")
    # A batch of its own: SQLite's batch mode can't put a constraint on a column renamed in
    # the same batch.
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f("uq_payments_session_id"), ["session_id"])
    op.execute(f"UPDATE payments SET amount_cents = amount_cents / {RIAL_PER_CENT}")
    # Old gateways can't be settled any more.
    op.execute("UPDATE payments SET status = 'failed' WHERE status = 'pending'")

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column(
            "price",
            existing_type=sa.Numeric(precision=14, scale=0),
            type_=sa.Numeric(precision=14, scale=2),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column(
            "price",
            existing_type=sa.Numeric(precision=14, scale=2),
            type_=sa.Numeric(precision=14, scale=0),
        )

    op.execute(f"UPDATE payments SET amount_cents = amount_cents * {RIAL_PER_CENT}")
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_payments_session_id"), type_="unique")
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("card_pan", sa.String(length=32), nullable=True))
        batch_op.alter_column(
            "ref_id", existing_type=sa.String(length=255), type_=sa.String(length=64)
        )
        batch_op.alter_column(
            "session_id",
            new_column_name="authority",
            existing_type=sa.String(length=255),
            type_=sa.String(length=64),
        )
        batch_op.alter_column("amount_cents", new_column_name="amount_rial")
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f("uq_payments_authority"), ["authority"])

    op.execute(
        "UPDATE wallet_entries SET "
        f"amount_cents = amount_cents * {RIAL_PER_CENT}, "
        f"balance_after_cents = balance_after_cents * {RIAL_PER_CENT}"
    )
    with op.batch_alter_table("wallet_entries", schema=None) as batch_op:
        batch_op.alter_column("amount_cents", new_column_name="amount_rial")
        batch_op.alter_column("balance_after_cents", new_column_name="balance_after_rial")

    op.execute(f"UPDATE shops SET balance_cents = balance_cents * {RIAL_PER_CENT}")
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("currency")
        batch_op.alter_column("balance_cents", new_column_name="balance_rial")
