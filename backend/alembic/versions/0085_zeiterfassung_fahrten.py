"""Zeiterfassung Stufe 3 (docs/konzepte/ZEITERFASSUNG.md): Fahrten mit km.

Neue Felder an zeiterfassung: km (nur bei kategorie='fahrzeit' sinnvoll,
Pruefung sitzt in der Route/im Schema, nicht als CHECK -- die Kategorie
kann sich per PATCH aendern), fahrzeug_id (FK auf anlagen, nur Anlagen mit
objekttyp='fahrzeug'), quelle ('timer'|'manuell', ausschliesslich vom
Server gesetzt, nie per API aenderbar).

Altbestand (Konzept 5.1, mit dem Nutzer abgestimmt): quelle wird 'timer'
fuer Eintraege, die ueber ein vorgang_events-Ereignis vom Typ 'zeit_start'
entstanden sind, sonst 'manuell' (Spalten-Default).

Revision ID: 0085
Revises: 0084
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("zeiterfassung", sa.Column("km", sa.Numeric(7, 1), nullable=True))
    op.create_check_constraint(
        "km_nicht_negativ", "zeiterfassung", "km IS NULL OR km >= 0"
    )
    op.add_column(
        "zeiterfassung", sa.Column("fahrzeug_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_zeiterfassung_fahrzeug_id_anlagen", "zeiterfassung", "anlagen", ["fahrzeug_id"], ["id"]
    )
    op.add_column(
        "zeiterfassung", sa.Column("quelle", sa.Text(), nullable=False, server_default="manuell")
    )
    op.create_check_constraint(
        "quelle_valid", "zeiterfassung", "quelle IN ('timer', 'manuell')"
    )

    op.execute(
        """
        UPDATE zeiterfassung z
        SET quelle = 'timer'
        WHERE EXISTS (
            SELECT 1 FROM vorgang_events v
            WHERE v.event_type = 'zeit_start' AND v.payload ->> 'zeiterfassung_id' = z.id::text
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_zeiterfassung_quelle_valid", "zeiterfassung", type_="check")
    op.drop_column("zeiterfassung", "quelle")
    op.drop_constraint("fk_zeiterfassung_fahrzeug_id_anlagen", "zeiterfassung", type_="foreignkey")
    op.drop_column("zeiterfassung", "fahrzeug_id")
    op.drop_constraint("ck_zeiterfassung_km_nicht_negativ", "zeiterfassung", type_="check")
    op.drop_column("zeiterfassung", "km")
