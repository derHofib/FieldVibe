"""Zeiterfassung: manuelle Eintraege ohne Vorgangsbezug (Kategorien)

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("zeiterfassung", "vorgang_id", nullable=True)
    op.add_column(
        "zeiterfassung",
        sa.Column("kategorie", sa.Text(), nullable=False, server_default="auftrag"),
    )
    op.execute(
        "ALTER TABLE zeiterfassung ADD CONSTRAINT ck_zeiterfassung_kategorie_valid "
        "CHECK (kategorie IN ('auftrag', 'verwaltung', 'fahrzeit', 'schulung', "
        "'urlaub', 'krankheit', 'sonstiges'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE zeiterfassung DROP CONSTRAINT ck_zeiterfassung_kategorie_valid")
    op.drop_column("zeiterfassung", "kategorie")
    op.execute("DELETE FROM zeiterfassung WHERE vorgang_id IS NULL")
    op.alter_column("zeiterfassung", "vorgang_id", nullable=False)
