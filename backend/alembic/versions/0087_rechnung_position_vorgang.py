"""Sammelrechnung: rechnung_positionen.vorgang_id.

Eine Rechnung kann Positionen aus mehreren Vorgaengen desselben Kunden
tragen (rechnungen.vorgang_id bleibt dann NULL). Damit das Entfernen einer
Position nur die Zeiterfassung-Eintraege des jeweiligen Vorgangs wieder
entsperrt, merkt sich jede aus Zeit/Fahrzeit/Fahrtkosten/Leistung
uebernommene Position ihren Vorgang.

Backfill: bisherige Positionen mit quelle uebernehmen den Vorgang ihrer
Rechnung -- das war bisher der einzige Weg, wie sie entstehen konnten.

Revision ID: 0087
Revises: 0086
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0087"
down_revision: Union[str, None] = "0086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rechnung_positionen",
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rechnung_positionen_vorgang_id_vorgaenge",
        "rechnung_positionen",
        "vorgaenge",
        ["vorgang_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_rechnung_positionen_vorgang_id", "rechnung_positionen", ["vorgang_id"])
    op.execute(
        """
        UPDATE rechnung_positionen p SET vorgang_id = r.vorgang_id
        FROM rechnungen r
        WHERE p.rechnung_id = r.id AND r.vorgang_id IS NOT NULL AND p.quelle IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_rechnung_positionen_vorgang_id", table_name="rechnung_positionen")
    op.drop_constraint(
        "fk_rechnung_positionen_vorgang_id_vorgaenge", "rechnung_positionen", type_="foreignkey"
    )
    op.drop_column("rechnung_positionen", "vorgang_id")
