"""add constraints and enums to users

Revision ID: cb9f2005a826
Revises: 265a29d7d6a2
Create Date: 2026-02-16 21:16:28.412674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cb9f2005a826'
down_revision: Union[str, Sequence[str], None] = '265a29d7d6a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():

    # Create ENUM type first
    subscription_enum = postgresql.ENUM(
        'FREE', 'PRO', 'PREMIUM',
        name='subscriptionenum'
    )
    subscription_enum.create(op.get_bind())

    # Add column using created ENUM
    op.add_column(
        'users',
        sa.Column(
            'subscription',
            sa.Enum(
                'FREE', 'PRO', 'PREMIUM',
                name='subscriptionenum'
            ),
            nullable=False,
            server_default='FREE'
        )
    )

def downgrade():

    op.drop_column('users', 'subscription')

    subscription_enum = postgresql.ENUM(
        'FREE', 'PRO', 'PREMIUM',
        name='subscriptionenum'
    )
    subscription_enum.drop(op.get_bind())