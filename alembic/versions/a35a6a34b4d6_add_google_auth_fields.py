"""add_google_auth_fields

Revision ID: a35a6a34b4d6
Revises: 04dfb92c2156
Create Date: 2026-06-11 17:22:50.423393

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a35a6a34b4d6'
down_revision: Union[str, Sequence[str], None] = '0c98ff7f1c1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():

    op.add_column(
        "users",
        sa.Column(
            "provider",
            sa.String(),
            nullable=True,
            server_default="email"
        )
    )

    # Fill existing users
    op.execute(
        "UPDATE users SET provider = 'email' WHERE provider IS NULL"
    )

    # Make column NOT NULL
    op.alter_column(
        "users",
        "provider",
        nullable=False
    )

    op.add_column(
        "users",
        sa.Column(
            "google_id",
            sa.String(),
            nullable=True
        )
    )

    op.alter_column(
        "users",
        "password",
        existing_type=sa.String(),
        nullable=True
    )

    op.create_unique_constraint(
        "uq_users_google_id",
        "users",
        ["google_id"]
    )


def downgrade():

    op.drop_constraint(
        "uq_users_google_id",
        "users",
        type_="unique"
    )

    op.alter_column(
        "users",
        "password",
        existing_type=sa.String(),
        nullable=False
    )

    op.drop_column("users", "google_id")
    op.drop_column("users", "provider")