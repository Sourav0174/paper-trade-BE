"""add_partial_indexes_for_pending_orders

Revision ID: ccb64685ef4e
Revises: 7f8e9d0c1a2b
Create Date: 2026-09-14 21:56:43.268981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccb64685ef4e'
down_revision: Union[str, Sequence[str], None] = '7f8e9d0c1a2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_orders_pending_expiry',
        'orders',
        ['expires_at', 'created_at'],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'")
    )
    op.create_index(
        'ix_orders_pending_execution',
        'orders',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING' AND order_type = 'LIMIT'")
    )


def downgrade() -> None:
    op.drop_index('ix_orders_pending_execution', table_name='orders')
    op.drop_index('ix_orders_pending_expiry', table_name='orders')

