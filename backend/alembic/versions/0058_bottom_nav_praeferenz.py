"""Individualisierbare Bottom-Nav (siehe app/models/user.py): je Nutzer
optional gespeicherte, geordnete Liste der Seiten-Keys, die in der unteren
Navigationsleiste sichtbar sein sollen. NULL = weiterhin die bisherige
Standardauswahl verwenden, damit bestehende Nutzer ohne Aenderung
weiterarbeiten.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("bottom_nav_items", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "bottom_nav_items")
