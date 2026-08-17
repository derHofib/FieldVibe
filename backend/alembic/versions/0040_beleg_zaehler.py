"""Atomarer Nummernkreis je Mandant + Belegart als eigene Tabelle --
ersetzt die bisherige COUNT(*)-basierte Rechnungsnummer-Vergabe, die unter
Nebenlaeufigkeit (zwei parallele Anfragen lesen denselben Zaehlerstand)
zu einer verletzten Unique-Constraint fuehren konnte. Backfill uebernimmt
fuer bereits bestehende Rechnungen den naechsten freien Zaehlerstand,
damit die Nummerierung luckenlos an der bisherigen COUNT(*)-Logik anschliesst.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beleg_zaehler",
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mandanten.id"), primary_key=True),
        sa.Column("belegart", sa.Text(), primary_key=True),
        sa.Column("naechste_nummer", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        """
        INSERT INTO beleg_zaehler (mandant_id, belegart, naechste_nummer)
        SELECT mandant_id, 'rechnung', COUNT(*) + 1
        FROM rechnungen
        GROUP BY mandant_id
        """
    )


def downgrade() -> None:
    op.drop_table("beleg_zaehler")
