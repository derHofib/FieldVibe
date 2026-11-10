"""Steuer je Rechnungsposition: steuer_kategorie und steuer_satz.

Bisher galt ein Satz je Beleg (rechnungen.mwst_satz). Gemischte Belege
(z. B. 19 % und 7 %) brauchen den Satz je Position; die Kategorien folgen
EN 16931 / UNTDID 5305 (S, Z, E, AE). Backfill je Position aus dem Beleg:
Satz = rechnungen.mwst_satz, Kategorie 'E' bei Satz 0 (Altbestand mit Satz 0
ist Kleinunternehmer, die E-Rechnung exportierte das bereits als Befreiung),
sonst 'S'. Bereits versendete Rechnungen aendern sich inhaltlich nicht -- nur
die neuen Spalten kommen hinzu; rechnungen.mwst_satz bleibt Vorbelegung und
Satz fuer Rechnungen ohne Positionen.

Revision ID: 0104
Revises: 0103
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0104"
down_revision: Union[str, None] = "0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLE = "rechnung_positionen"
# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CHECKS = (
    ("steuer_kategorie_valid", "steuer_kategorie IN ('S', 'Z', 'E', 'AE')"),
    ("steuer_satz_zu_kategorie", "steuer_kategorie = 'S' OR steuer_satz = 0"),
    ("steuer_satz_bereich", "steuer_satz >= 0 AND steuer_satz <= 100"),
)


def backfill_steuer(connection: sa.engine.Connection) -> None:
    connection.execute(
        sa.text(
            f"""
            UPDATE {_TABELLE} AS p
            SET steuer_satz = r.mwst_satz,
                steuer_kategorie = CASE WHEN r.mwst_satz = 0 THEN 'E' ELSE 'S' END
            FROM rechnungen AS r
            WHERE r.id = p.rechnung_id
            """
        )
    )


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    # Erst nullable, damit der Backfill vor NOT NULL laufen kann. Der
    # Server-Default gilt nur fuer die Kategorie (S ist der Regelfall); der
    # Satz wird beim Anlegen immer explizit gesetzt.
    op.add_column(_TABELLE, sa.Column("steuer_kategorie", sa.Text(), nullable=True))
    op.add_column(_TABELLE, sa.Column("steuer_satz", sa.Numeric(5, 2), nullable=True))
    backfill_steuer(op.get_bind())
    op.alter_column(_TABELLE, "steuer_kategorie", nullable=False, server_default="S")
    op.alter_column(_TABELLE, "steuer_satz", nullable=False)
    for name, bedingung in _CHECKS:
        op.create_check_constraint(name, _TABELLE, bedingung)


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    for name, _ in reversed(_CHECKS):
        op.drop_constraint(name, _TABELLE, type_="check")
    op.drop_column(_TABELLE, "steuer_satz")
    op.drop_column(_TABELLE, "steuer_kategorie")
