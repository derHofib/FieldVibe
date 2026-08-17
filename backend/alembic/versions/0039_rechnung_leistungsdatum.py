"""Leistungsdatum/-zeitraum als eigenes Feld an der Rechnung -- Pflichtangabe
nach §14 Abs. 4 Nr. 6 UStG, die bislang auf keiner FieldVibe-Rechnung
ausgewiesen wurde.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rechnungen", sa.Column("leistungsdatum", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("rechnungen", "leistungsdatum")
