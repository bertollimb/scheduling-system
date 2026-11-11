"""make client phone optional

Revision ID: a3f9c2d41b7e
Revises: 1eb1b7b3025a
Create Date: 2026-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c2d41b7e'
down_revision: Union[str, Sequence[str], None] = '1eb1b7b3025a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'clients',
        'phone',
        existing_type=sa.String(length=20),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Rows created while phone was optional may hold NULL, which would make
    # the NOT NULL constraint fail. Fill them with an empty string first.
    op.execute("UPDATE clients SET phone = '' WHERE phone IS NULL")
    op.alter_column(
        'clients',
        'phone',
        existing_type=sa.String(length=20),
        nullable=False,
    )