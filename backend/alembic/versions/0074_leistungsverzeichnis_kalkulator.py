"""Leistungsverzeichnis wird zum Kalkulator: Hierarchie + Lohn/Material-Split.

Drei Erweiterungen von leistungsverzeichnis_positionen:

1. kunde_id wird nullable -- NULL heisst "gilt fuer alle Kunden" (ein
   mandantenweiter Katalog fuer Standardleistungen wie "Installation
   Wallbox"), ein gesetzter Wert bleibt fuer kundenspezifische Sonder-
   konditionen moeglich.
2. eltern_position_id (selbstreferenzierend, ON DELETE CASCADE) fuer
   Unterpunkte -- bewusst nur eine Ebene tief, analog zu projekt_aufgaben.
   eltern_aufgabe_id. Ein Hauptpunkt (hat Kinder) bekommt seinen Preis rein
   rechnerisch als Summe seiner Unterpunkte; eigene Kalkulationsfelder
   werden dann applikationsseitig ignoriert (siehe app/api/routes/
   leistungsverzeichnis.py:_neu_berechnen).
3. Kalkulationsfelder fuer den Modus "berechnet" (Alternative zu
   "festpreis", dem bisherigen und weiterhin moeglichen manuellen
   Verhalten): lohn_minuten x lohn_stundensatz sowie eine freie Liste
   material_posten (JSONB, gleiches Prinzip wie projekt_aufgaben.
   checkliste) x material_aufschlag_prozent. lohn_gesamt/material_gesamt
   sind das serverseitig gepflegte Ergebnis -- Grundlage fuer den
   automatischen Lohn/Material-Split beim Uebernehmen in ein Angebot.
   einzelpreis bleibt die etablierte Spalte (Zeiterfassung/Verwendung lesen
   sie unveraendert) und wird im Modus "berechnet" bzw. bei vorhandenen
   Kindern serverseitig ueberschrieben statt frei editierbar zu sein.

Revision ID: 0074
Revises: 0073
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0074"
down_revision: Union[str, None] = "0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("leistungsverzeichnis_positionen", "kunde_id", nullable=True)

    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("eltern_position_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("kalkulationsmodus", sa.Text(), nullable=False, server_default="festpreis"),
    )
    op.add_column(
        "leistungsverzeichnis_positionen", sa.Column("lohn_minuten", sa.Integer(), nullable=True)
    )
    op.add_column(
        "leistungsverzeichnis_positionen", sa.Column("lohn_stundensatz", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column(
            "material_posten", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column(
            "material_aufschlag_prozent", sa.Numeric(5, 2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("lohn_gesamt", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("material_gesamt", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )

    op.create_foreign_key(
        "fk_leistungsverzeichnis_positionen_eltern_position_id",
        "leistungsverzeichnis_positionen",
        "leistungsverzeichnis_positionen",
        ["eltern_position_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_leistungsverzeichnis_positionen_kalkulationsmodus_valid",
        "leistungsverzeichnis_positionen",
        "kalkulationsmodus IN ('festpreis', 'berechnet')",
    )
    op.create_index(
        "ix_leistungsverzeichnis_positionen_eltern_position_id",
        "leistungsverzeichnis_positionen",
        ["eltern_position_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_leistungsverzeichnis_positionen_eltern_position_id", table_name="leistungsverzeichnis_positionen")
    op.drop_constraint(
        "ck_leistungsverzeichnis_positionen_kalkulationsmodus_valid",
        "leistungsverzeichnis_positionen",
        type_="check",
    )
    op.drop_constraint(
        "fk_leistungsverzeichnis_positionen_eltern_position_id",
        "leistungsverzeichnis_positionen",
        type_="foreignkey",
    )

    op.drop_column("leistungsverzeichnis_positionen", "material_gesamt")
    op.drop_column("leistungsverzeichnis_positionen", "lohn_gesamt")
    op.drop_column("leistungsverzeichnis_positionen", "material_aufschlag_prozent")
    op.drop_column("leistungsverzeichnis_positionen", "material_posten")
    op.drop_column("leistungsverzeichnis_positionen", "lohn_stundensatz")
    op.drop_column("leistungsverzeichnis_positionen", "lohn_minuten")
    op.drop_column("leistungsverzeichnis_positionen", "kalkulationsmodus")
    op.drop_column("leistungsverzeichnis_positionen", "eltern_position_id")

    op.execute("DELETE FROM leistungsverzeichnis_positionen WHERE kunde_id IS NULL")
    op.alter_column("leistungsverzeichnis_positionen", "kunde_id", nullable=False)
