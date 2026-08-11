"""Indizes und Constraint-Erweiterung fuer die Rechnungsuebersicht.

Drei Dinge, die die neue Uebersicht (app/api/routes/rechnungen.py) und die
globale Suche brauchen:

1. Trigram-Index auf rechnungen.rechnungsnummer -- die Freitextsuche nach
   "R-00042" nutzt ILIKE plus similarity()-Ranking, genau wie die schon
   vorhandenen Typeahead-Indizes aus Migration 0003.
2. Zusammengesetzter Index (mandant_id, status, faellig_am) fuer die
   Ueberfaellig-/Offen-Filter und die Faelligkeitssortierung.
3. Die gespeicherten Filter kennen jetzt auch die Entitaet "rechnungen",
   damit sich Filtervorlagen wie "Alle ueberfaelligen" speichern lassen.
   Der CHECK-Constraint muss dafuer neu gesetzt werden.

Zu op.f(): die naming_convention aus app/db/base.py ist auch fuer Alembic
aktiv. Ohne op.f() wuerde Alembic den bereits vollstaendig praefixierten
Namen erneut praefixieren ("ck_gespeicherte_filter_ck_gespeicherte_..."),
siehe Migration 0022.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENTITAETEN_NEU = ("vorgaenge", "anlagen", "kunden", "standorte", "rechnungen")
_ENTITAETEN_ALT = ("vorgaenge", "anlagen", "kunden", "standorte")


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_rechnungen_rechnungsnummer_trgm "
        "ON rechnungen USING gin (rechnungsnummer gin_trgm_ops)"
    )
    op.create_index(
        "ix_rechnungen_mandant_status_faellig",
        "rechnungen",
        ["mandant_id", "status", "faellig_am"],
    )

    op.drop_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"), "gespeicherte_filter", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"),
        "gespeicherte_filter",
        f"entitaet IN {_ENTITAETEN_NEU}",
    )


def downgrade() -> None:
    # Vorlagen fuer Rechnungen muessen weg, bevor der engere Constraint
    # wieder greift -- sonst scheitert das CHECK an Bestandsdaten.
    op.execute("DELETE FROM gespeicherte_filter WHERE entitaet = 'rechnungen'")
    op.drop_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"), "gespeicherte_filter", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"),
        "gespeicherte_filter",
        f"entitaet IN {_ENTITAETEN_ALT}",
    )

    op.drop_index("ix_rechnungen_mandant_status_faellig", table_name="rechnungen")
    op.execute("DROP INDEX IF EXISTS ix_rechnungen_rechnungsnummer_trgm")
