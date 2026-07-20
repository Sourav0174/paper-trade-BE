"""add orders table and reservations

Revision ID: 5e38aba5c28f
Revises: a35a6a34b4d6
Create Date: 2026-07-20 11:55:14.896813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e38aba5c28f'
down_revision: Union[str, Sequence[str], None] = 'a35a6a34b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.add_column(
        'holdings',
        sa.Column(
            'reserved_quantity',
            sa.Integer(),
            nullable=False,
            server_default='0'
        )
    )

    op.add_column(
        'portfolios',
        sa.Column(
            'reserved_balance',
            sa.Float(),
            nullable=False,
            server_default='0'
        )
    )

    # sa.Enum's lifecycle is tied to this table: create_table/drop_table
    # below implicitly issue the matching CREATE TYPE / DROP TYPE.
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column(
            'trade_type',
            sa.Enum('BUY', 'SELL', name='order_trade_type'),
            nullable=False
        ),
        sa.Column(
            'order_type',
            sa.Enum('MARKET', 'LIMIT', name='order_type'),
            nullable=False
        ),
        sa.Column('limit_price', sa.Float(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'PENDING', 'EXECUTED', 'CANCELLED', 'EXPIRED', 'REJECTED',
                name='order_status'
            ),
            nullable=False,
            server_default='PENDING'
        ),
        sa.Column('executed_price', sa.Float(), nullable=True),
        sa.Column(
            'reserved_amount',
            sa.Float(),
            nullable=False,
            server_default='0'
        ),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('orders_pkey')),
    )

    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_orders_symbol'), 'orders', ['symbol'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_index(op.f('ix_orders_expires_at'), 'orders', ['expires_at'], unique=False)
    op.create_index(
        'ix_orders_user_id_status', 'orders', ['user_id', 'status'], unique=False
    )
    op.create_index(
        'ix_orders_symbol_status', 'orders', ['symbol', 'status'], unique=False
    )


def downgrade() -> None:

    op.drop_index('ix_orders_symbol_status', table_name='orders')
    op.drop_index('ix_orders_user_id_status', table_name='orders')
    op.drop_index(op.f('ix_orders_expires_at'), table_name='orders')
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_symbol'), table_name='orders')
    op.drop_index(op.f('ix_orders_user_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_id'), table_name='orders')
    op.drop_table('orders')

    op.drop_column('portfolios', 'reserved_balance')
    op.drop_column('holdings', 'reserved_quantity')
