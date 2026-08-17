"""Korrigiert doppelt praefixierte CHECK-Constraint-Namen (z.B.
"ck_vorgaenge_ck_vorgaenge_status_valid" statt "ck_vorgaenge_status_valid").

Ursache: env.py bindet target_metadata = Base.metadata, dessen
naming_convention (app/db/base.py) auch fuer Alembic-Migrationen aktiv ist.
Wird einer sa.CheckConstraint(..., name="ck_x_y") innerhalb von
op.create_table(...) ein bereits vollstaendig praefixierter Name mitgegeben
(statt ihn mit op.f(...) als "final" zu markieren), wendet Alembic die
Convention "ck_%(table_name)s_%(constraint_name)s" trotzdem erneut auf diesen
Namen an und erzeugt "ck_x_ck_x_y". Das betrifft praktisch jede so
deklarierte CHECK-Constraint seit Migration 0001 -- inhaltlich folgenlos
(die Bedingung selbst war immer korrekt), aber der Name war falsch. Diese
Migration benennt die betroffenen Constraints per ALTER TABLE ... RENAME
CONSTRAINT um, ohne sie zu droppen/neu anzulegen (keine Downtime, keine
Racebedingung mit laufendem Traffic).

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (Tabelle, falscher doppelt-praefixierter Name, korrekter Name)
_UMBENENNUNGEN = [
    ("angebote", "ck_angebote_ck_angebote_status_valid", "ck_angebote_status_valid"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_abrechnungsart_valid", "ck_dauerauftraege_abrechnungsart_valid"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_intervall_positiv", "ck_dauerauftraege_intervall_positiv"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_leistungstyp_valid", "ck_dauerauftraege_leistungstyp_valid"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_modus_valid", "ck_dauerauftraege_modus_valid"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_toleranz_frueh_positiv", "ck_dauerauftraege_toleranz_frueh_positiv"),
    ("dauerauftraege", "ck_dauerauftraege_ck_dauerauftraege_toleranz_spaet_positiv", "ck_dauerauftraege_toleranz_spaet_positiv"),
    ("inventurzyklen", "ck_inventurzyklen_ck_inventurzyklen_intervall_positiv", "ck_inventurzyklen_intervall_positiv"),
    ("kunden", "ck_kunden_ck_kunden_typ_valid", "ck_kunden_typ_valid"),
    ("maengel", "ck_maengel_ck_maengel_schweregrad_valid", "ck_maengel_schweregrad_valid"),
    ("maengel", "ck_maengel_ck_maengel_status_valid", "ck_maengel_status_valid"),
    ("mandant_rollen_rechte", "ck_mandant_rollen_rechte_ck_mandant_rollen_rechte_aktion_valid", "ck_mandant_rollen_rechte_aktion_valid"),
    ("mandant_rollen_rechte", "ck_mandant_rollen_rechte_ck_mandant_rollen_rechte_bereich_valid", "ck_mandant_rollen_rechte_bereich_valid"),
    ("mandant_rollen_rechte", "ck_mandant_rollen_rechte_ck_mandant_rollen_rechte_rolle_valid", "ck_mandant_rollen_rechte_rolle_valid"),
    ("mandanten", "ck_mandanten_ck_mandanten_scheduler_stunde_utc_valid", "ck_mandanten_scheduler_stunde_utc_valid"),
    ("mandanten", "ck_mandanten_ck_mandanten_status_valid", "ck_mandanten_status_valid"),
    ("material_bestand", "ck_material_bestand_ck_material_bestand_menge_nicht_negativ", "ck_material_bestand_menge_nicht_negativ"),
    ("material_bewegungen", "ck_material_bewegungen_ck_material_bewegungen_menge_positiv", "ck_material_bewegungen_menge_positiv"),
    ("material_bewegungen", "ck_material_bewegungen_ck_material_bewegungen_typ_valid", "ck_material_bewegungen_typ_valid"),
    ("material_verwendungen", "ck_material_verwendungen_ck_material_verwendungen_menge_positiv", "ck_material_verwendungen_menge_positiv"),
    ("pruefmittel", "ck_pruefmittel_ck_pruefmittel_intervall_positiv", "ck_pruefmittel_intervall_positiv"),
    ("pruefmittel", "ck_pruefmittel_ck_pruefmittel_status_valid", "ck_pruefmittel_status_valid"),
    ("pruefzyklen", "ck_pruefzyklen_ck_pruefzyklen_intervall_positiv", "ck_pruefzyklen_intervall_positiv"),
    ("rechnungen", "ck_rechnungen_ck_rechnungen_status_valid", "ck_rechnungen_status_valid"),
    ("tag_assignments", "ck_tag_assignments_ck_tag_assignments_entity_type_valid", "ck_tag_assignments_entity_type_valid"),
    ("termine", "ck_termine_ck_termine_ende_after_start", "ck_termine_ende_after_start"),
    ("termine", "ck_termine_ck_termine_status_valid", "ck_termine_status_valid"),
    ("vertraege", "ck_vertraege_ck_vertraege_abrechnungsart_valid", "ck_vertraege_abrechnungsart_valid"),
    ("vorgaenge", "ck_vorgaenge_ck_vorgaenge_abrechnungsart_valid", "ck_vorgaenge_abrechnungsart_valid"),
    ("vorgaenge", "ck_vorgaenge_ck_vorgaenge_leistungstyp_valid", "ck_vorgaenge_leistungstyp_valid"),
    ("vorgaenge", "ck_vorgaenge_ck_vorgaenge_status_valid", "ck_vorgaenge_status_valid"),
    ("vorgang_anfragen", "ck_vorgang_anfragen_ck_vorgang_anfragen_leistungstyp_valid", "ck_vorgang_anfragen_leistungstyp_valid"),
    ("vorgang_anfragen", "ck_vorgang_anfragen_ck_vorgang_anfragen_status_valid", "ck_vorgang_anfragen_status_valid"),
    ("vorgang_events", "ck_vorgang_events_ck_vorgang_events_event_type_valid", "ck_vorgang_events_event_type_valid"),
    ("zeiterfassung", "ck_zeiterfassung_ck_zeiterfassung_ende_after_start", "ck_zeiterfassung_ende_after_start"),
]


def upgrade() -> None:
    for tabelle, falsch, richtig in _UMBENENNUNGEN:
        # IF EXISTS-Pruefung per DO-Block: eine Umgebung, die bereits einmal
        # manuell korrigiert wurde (oder bei der der Bug aus anderen Gruenden
        # nie zuschlug), darf beim erneuten Ausfuehren nicht mit "constraint
        # does not exist" abbrechen.
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{falsch}'
                  AND conrelid = '{tabelle}'::regclass
              ) THEN
                ALTER TABLE {tabelle} RENAME CONSTRAINT {falsch} TO {richtig};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for tabelle, falsch, richtig in _UMBENENNUNGEN:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{richtig}'
                  AND conrelid = '{tabelle}'::regclass
              ) THEN
                ALTER TABLE {tabelle} RENAME CONSTRAINT {richtig} TO {falsch};
              END IF;
            END $$;
            """
        )
