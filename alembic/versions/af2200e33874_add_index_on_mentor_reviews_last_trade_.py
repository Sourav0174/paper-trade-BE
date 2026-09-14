"""add_index_on_mentor_reviews_last_trade_id

Revision ID: af2200e33874
Revises: ccb64685ef4e
Create Date: 2026-09-15 00:45:33.248464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af2200e33874'
down_revision: Union[str, Sequence[str], None] = 'ccb64685ef4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_mentor_reviews_last_trade_id'),
        'mentor_reviews',
        ['last_trade_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_mentor_reviews_last_trade_id'),
        table_name='mentor_reviews',
    )

