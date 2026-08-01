"""add mentor reviews table

Revision ID: 7f8e9d0c1a2b
Revises: 5e38aba5c28f
Create Date: 2026-08-01 16:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f8e9d0c1a2b'
down_revision: Union[str, Sequence[str], None] = '5e38aba5c28f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mentor_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('review_type', sa.String(), nullable=False, server_default='DAILY'),
        sa.Column('health_score', sa.Float(), nullable=False),
        sa.Column('trading_grade', sa.String(), nullable=False),
        sa.Column('summary_json', sa.JSON(), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=False),
        sa.Column('trade_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_trade_id', sa.String(), nullable=True),
        sa.Column('stale', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id', name=op.f('mentor_reviews_pkey')),
    )
    op.create_index(op.f('ix_mentor_reviews_id'), 'mentor_reviews', ['id'], unique=False)
    op.create_index(op.f('ix_mentor_reviews_user_id'), 'mentor_reviews', ['user_id'], unique=False)
    op.create_index(op.f('ix_mentor_reviews_review_type'), 'mentor_reviews', ['review_type'], unique=False)
    op.create_index(op.f('ix_mentor_reviews_stale'), 'mentor_reviews', ['stale'], unique=False)
    op.create_index(op.f('ix_mentor_reviews_generated_at'), 'mentor_reviews', ['generated_at'], unique=False)
    op.create_index('ix_mentor_reviews_user_type', 'mentor_reviews', ['user_id', 'review_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mentor_reviews_user_type', table_name='mentor_reviews')
    op.drop_index(op.f('ix_mentor_reviews_generated_at'), table_name='mentor_reviews')
    op.drop_index(op.f('ix_mentor_reviews_stale'), table_name='mentor_reviews')
    op.drop_index(op.f('ix_mentor_reviews_review_type'), table_name='mentor_reviews')
    op.drop_index(op.f('ix_mentor_reviews_user_id'), table_name='mentor_reviews')
    op.drop_index(op.f('ix_mentor_reviews_id'), table_name='mentor_reviews')
    op.drop_table('mentor_reviews')
