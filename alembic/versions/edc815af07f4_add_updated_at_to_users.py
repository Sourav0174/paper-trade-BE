"""add updated_at to users

Revision ID: edc815af07f4
Revises: cb9f2005a826
Create Date: 2026-02-17 20:00:34.424899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'edc815af07f4'
down_revision: Union[str, Sequence[str], None] = 'cb9f2005a826'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        )
    )

def downgrade() -> None:
    op.drop_column('users', 'updated_at')