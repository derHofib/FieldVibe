"""Zeiterfassung Stufe 4 (docs/konzepte/ZEITERFASSUNG.md): Abrechnung.

Mandanten-Einstellungen fuer die Fahrzeit-Abrechnung (Abschnitt 5.3):
km_satz_netto (Euro/km fuer Fahrtkosten-Vorschlaege) und
fahrzeit_abrechnung ('keine'|'zeit'|'km'|'zeit_und_km', Default 'keine' --
aendert fuer bestehende Mandanten nichts, bis ein Admin es aktiv einstellt).

zeiterfassung.abgerechnet_rechnung_id verknuepft einen Eintrag mit der
Rechnung, die ihn ueber eine "zeit"/"fahrzeit"/"fahrtkosten"-Position
uebernommen hat (Abschnitt 8) -- Grundlage fuer das Sperren/Entsperren beim
Uebernehmen bzw. Entfernen einer Rechnungsposition.

rechnung_positionen.quelle haelt fest, aus welchem Rechnungsvorschlag eine
Position uebernommen wurde (NULL bei manuell eingetragenen Positionen) --
noetig, um beim Entfernen einer Position zu wissen, welche Zeiterfassung-
Eintraege ggf. wieder auf 'gebucht' zurueckgesetzt werden muessen.

Revision ID: 0086
Revises: 0085
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0086"
down_revision: Union[str, None] = "0085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mandanten", sa.Column("km_satz_netto", sa.Numeric(6, 2), nullable=True))
    op.create_check_constraint(
        "km_satz_netto_nicht_negativ", "mandanten", "km_satz_netto IS NULL OR km_satz_netto >= 0"
    )
    op.add_column(
        "mandanten",
        sa.Column("fahrzeit_abrechnung", sa.Text(), nullable=False, server_default="keine"),
    )
    op.create_check_constraint(
        "fahrzeit_abrechnung_valid",
        "mandanten",
        "fahrzeit_abrechnung IN ('keine', 'zeit', 'km', 'zeit_und_km')",
    )

    op.add_column(
        "zeiterfassung",
        sa.Column("abgerechnet_rechnung_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_zeiterfassung_abgerechnet_rechnung_id_rechnungen",
        "zeiterfassung",
        "rechnungen",
        ["abgerechnet_rechnung_id"],
        ["id"],
    )
    op.create_index(
        "ix_zeiterfassung_abgerechnet_rechnung_id",
        "zeiterfassung",
        ["abgerechnet_rechnung_id"],
    )

    op.add_column("rechnung_positionen", sa.Column("quelle", sa.Text(), nullable=True))
    op.create_check_constraint(
        "quelle_valid",
        "rechnung_positionen",
        "quelle IS NULL OR quelle IN ('material', 'zeit', 'fahrzeit', 'fahrtkosten', 'leistung')",
    )

    # Neue Aktion fuers Protokoll: das Zurueckstellen einer Rechnungsposition
    # setzt betroffene Eintraege von 'abgerechnet' zurueck auf 'gebucht'
    # (siehe app/services/rechnung_service.zeiterfassung_abrechnung_zuruecksetzen).
    #
    # Das inline CheckConstraint(name=...) in Migration 0084 hat den bereits
    # praefigierten Namen "ck_zeiterfassung_aenderungen_aktion_valid" erneut
    # durch die Naming-Convention gejagt (derselbe Doppel-Praefix-Fehler wie
    # in 0083, siehe dortiger Kommentar) -- Postgres hat das Ergebnis auf 63
    # Zeichen gekuerzt/gehasht, der genaue Name ist also nicht verlaesslich
    # vorhersagbar. op.drop_constraint(..., type_="check") kann ihn ohnehin
    # nicht direkt ansprechen (baut selbst wieder ein CheckConstraint-Objekt
    # und laesst die Naming-Convention/Truncation erneut ueber den
    # uebergebenen String laufen). Stattdessen den tatsaechlich vorhandenen
    # Namen zur Laufzeit nachschlagen und per rohem SQL droppen -- robust
    # unabhaengig davon, ob die DB noch den kaputten oder (nach einem
    # frueheren Downgrade dieser Migration) bereits den sauberen Namen hat.
    op.execute(
        """
        DO $$
        DECLARE
            bestehender_name text;
        BEGIN
            SELECT conname INTO bestehender_name FROM pg_constraint
            WHERE conrelid = 'zeiterfassung_aenderungen'::regclass AND contype = 'c';
            IF bestehender_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE zeiterfassung_aenderungen DROP CONSTRAINT %I', bestehender_name);
            END IF;
        END $$;
        """
    )
    op.create_check_constraint(
        "aktion_valid",
        "zeiterfassung_aenderungen",
        "aktion IN ('angelegt', 'geaendert', 'geloescht', 'wiederhergestellt', 'vorgemerkt', "
        "'vormerkung_zurueckgezogen', 'gebucht', 'buchung_storniert', 'abgerechnet', "
        "'abrechnung_zurueckgesetzt')",
    )


def downgrade() -> None:
    op.drop_constraint("aktion_valid", "zeiterfassung_aenderungen", type_="check")
    op.create_check_constraint(
        "aktion_valid",
        "zeiterfassung_aenderungen",
        "aktion IN ('angelegt', 'geaendert', 'geloescht', 'wiederhergestellt', 'vorgemerkt', "
        "'vormerkung_zurueckgezogen', 'gebucht', 'buchung_storniert', 'abgerechnet')",
    )

    op.drop_constraint("quelle_valid", "rechnung_positionen", type_="check")
    op.drop_column("rechnung_positionen", "quelle")

    op.drop_index("ix_zeiterfassung_abgerechnet_rechnung_id", table_name="zeiterfassung")
    op.drop_constraint(
        "fk_zeiterfassung_abgerechnet_rechnung_id_rechnungen", "zeiterfassung", type_="foreignkey"
    )
    op.drop_column("zeiterfassung", "abgerechnet_rechnung_id")

    op.drop_constraint("fahrzeit_abrechnung_valid", "mandanten", type_="check")
    op.drop_column("mandanten", "fahrzeit_abrechnung")
    op.drop_constraint("km_satz_netto_nicht_negativ", "mandanten", type_="check")
    op.drop_column("mandanten", "km_satz_netto")
