"""Individualisierbare Office-Sidebar (siehe app/models/user.py, analog zu
0059 bottom_nav_praeferenz): je Nutzer optional gespeicherte Liste der
Seiten-Keys, die in der Office-Seitenleiste angezeigt werden sollen. NULL =
weiterhin alle sichtbaren Seiten zeigen (bisheriges Verhalten), damit
bestehende Nutzer ohne Aenderung weiterarbeiten.

Revision ID: 0065
Revises: 0064
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("office_nav_items", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "office_nav_items")
