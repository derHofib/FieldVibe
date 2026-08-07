"""Zeiterfassung: keine Drittbestaetigung mehr, Pause-Kategorie

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("zeiterfassung", "freigegeben")
    op.execute("ALTER TABLE zeiterfassung DROP CONSTRAINT ck_zeiterfassung_kategorie_valid")
    op.execute(
        "ALTER TABLE zeiterfassung ADD CONSTRAINT ck_zeiterfassung_kategorie_valid "
        "CHECK (kategorie IN ('auftrag', 'verwaltung', 'fahrzeit', 'schulung', 'pause', "
        "'urlaub', 'krankheit', 'sonstiges'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE zeiterfassung DROP CONSTRAINT ck_zeiterfassung_kategorie_valid")
    op.execute("DELETE FROM zeiterfassung WHERE kategorie = 'pause'")
    op.execute(
        "ALTER TABLE zeiterfassung ADD CONSTRAINT ck_zeiterfassung_kategorie_valid "
        "CHECK (kategorie IN ('auftrag', 'verwaltung', 'fahrzeit', 'schulung', "
        "'urlaub', 'krankheit', 'sonstiges'))"
    )
    op.add_column(
        "zeiterfassung",
        sa.Column("freigegeben", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
