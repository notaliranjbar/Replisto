"""remove telegram, bale and plans

Replisto runs on Instagram only: the Telegram/Bale bots, the owner's linked messenger accounts,
channel posts and the paid plans (which only unlocked Telegram features) are gone. Data that
pointed at them is cleaned up first, so the remaining rows still load:
- Telegram/Bale conversations (and their messages) are deleted;
- products learned from channel posts count as taught ones;
- past plan fees stay in the wallet history as adjustments.

The removal is one way: downgrading would need the deleted data back.

Revision ID: 56c471d7558e
Revises: 89540fadc159
Create Date: 2026-10-08 11:24:52.194400

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "56c471d7558e"
down_revision: Union[str, Sequence[str], None] = "89540fadc159"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "DELETE FROM messages WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE channel IN ('telegram', 'bale'))"
    )
    op.execute("DELETE FROM conversations WHERE channel IN ('telegram', 'bale')")
    op.execute("UPDATE products SET origin = 'teach' WHERE origin = 'telegram_post'")
    op.execute("UPDATE wallet_entries SET kind = 'adjustment' WHERE kind = 'plan_fee'")

    # Columns that reference telegram_posts go before the table itself.
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_products_telegram_post_id_telegram_posts"), type_="foreignkey"
        )
        batch_op.drop_column("telegram_post_id")

    with op.batch_alter_table("teach_proposals", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_teach_proposals_telegram_post_id_telegram_posts"), type_="foreignkey"
        )
        batch_op.drop_column("telegram_post_id")

    # Tables that reference telegram_bots go before it.
    op.drop_table("telegram_sessions")
    for table in (
        "telegram_business_connections",
        "telegram_channels",
        "telegram_posts",
        "telegram_admins",
        "telegram_bots",
    ):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table}_shop_id"))
        op.drop_table(table)

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_shops_slug"), type_="unique")
        batch_op.drop_constraint(batch_op.f("uq_shops_telegram_link_code"), type_="unique")
        batch_op.drop_column("slug")
        batch_op.drop_column("telegram_enabled")
        batch_op.drop_column("bale_enabled")
        batch_op.drop_column("telegram_link_code")
        batch_op.drop_column("telegram_link_expires_at")
        batch_op.drop_column("plan")
        batch_op.drop_column("plan_renews_at")
        batch_op.drop_column("plan_next")


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError("Telegram, Bale and plans were removed; this can't be undone.")
