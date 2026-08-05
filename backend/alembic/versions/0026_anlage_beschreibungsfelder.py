"""Universelle Beschreibungsfelder fuer Anlagen (Hersteller, Modell,
Seriennummer, Anschaffungsdatum, Notiz) -- unabhaengig vom konkreten
Anlagentyp (Fahrzeug, Ladestation, Geraet, Elektroanlage, ...).

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("anlagen", sa.Column("hersteller", sa.Text(), nullable=True))
    op.add_column("anlagen", sa.Column("modell", sa.Text(), nullable=True))
    op.add_column("anlagen", sa.Column("seriennummer", sa.Text(), nullable=True))
    op.add_column("anlagen", sa.Column("anschaffungsdatum", sa.Date(), nullable=True))
    op.add_column("anlagen", sa.Column("notiz", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("anlagen", "notiz")
    op.drop_column("anlagen", "anschaffungsdatum")
    op.drop_column("anlagen", "seriennummer")
    op.drop_column("anlagen", "modell")
    op.drop_column("anlagen", "hersteller")
