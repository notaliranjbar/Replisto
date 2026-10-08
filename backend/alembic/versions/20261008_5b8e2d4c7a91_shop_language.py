"""shop language

The owner's panel language on the shop: the bot writes handoff reasons and summaries of what
it learned for the owner in it.

Revision ID: 5b8e2d4c7a91
Revises: 3f1c9a7d2b6e
Create Date: 2026-10-08 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5b8e2d4c7a91"
down_revision: Union[str, Sequence[str], None] = "3f1c9a7d2b6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("language", sa.String(length=2), server_default="en", nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("language")
