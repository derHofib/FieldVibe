"""Optionale Adresse direkt am Vorgang, damit fuer einen einmaligen Auftrag
nicht zwingend ein Standort angelegt werden muss.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vorgaenge", sa.Column("adresse", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("vorgaenge", "adresse")
