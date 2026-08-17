"""Firmenstammdaten (Adresse/Kontakt/Bank/Rechtliches) + Logo je Mandant fuer
einen professionellen Angebots-Briefkopf, sowie ein optionales
Artikelnummer-Feld je Angebotsposition fuer die neue "Art-Nr."-Spalte.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mandanten",
        sa.Column(
            "firmendaten", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column("mandanten", sa.Column("logo_object_key", sa.Text(), nullable=True))
    op.add_column("angebot_positionen", sa.Column("artikelnummer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("angebot_positionen", "artikelnummer")
    op.drop_column("mandanten", "logo_object_key")
    op.drop_column("mandanten", "firmendaten")
