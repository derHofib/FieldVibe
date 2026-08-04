"""Papierkorb: geloescht_am/geloescht_von (Soft-Delete) auf allen 21
fachlichen Kern-Tabellen sowie zwei neue Rollen (loesch_ansicht,
loesch_operativ) mit Erweiterung der role-Check-Constraint und einem
partial unique index, der je Mandant hoechstens einen aktiven
loesch_operativ-Account erlaubt.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Alle Tabellen, die "fachliche Daten" im Sinne des Papierkorbs tragen (siehe
# app/services/papierkorb_service.py). Bewusst NICHT dabei: System-/Log-/
# Beleg-Tabellen (users, mandanten, audit_log, notifications, integrationen,
# gespeicherte_filter, mandant_rollen_rechte, kundenportal_zugaenge,
# highlights, vorgang_events, zeiterfassungen) sowie reine Detailzeilen ohne
# eigene Sichtbarkeit (angebot_positionen, rechnung_positionen,
# bestellung_positionen, material_bestand/-bewegungen/-verwendungen,
# tag_assignments, kunde_zuweisungen).
_TABELLEN = (
    "kunden",
    "anlagen",
    "vertraege",
    "vorgaenge",
    "standorte",
    "termine",
    "pruefzyklen",
    "pruefmittel",
    "lieferanten",
    "material",
    "material_bedarfe",
    "bestellungen",
    "dauerauftraege",
    "dauerauftrag_ziele",
    "maengel",
    "angebote",
    "rechnungen",
    "inventurzyklen",
    "fahrzeug_zuweisungen",
    "tags",
    "vorgang_anfragen",
)

ROLES_NEU = (
    "super_admin",
    "mandant_admin",
    "disponent",
    "techniker",
    "controller",
    "mitarbeiter",
    "loesch_ansicht",
    "loesch_operativ",
)


def upgrade() -> None:
    for tabelle in _TABELLEN:
        op.add_column(
            tabelle, sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True)
        )
        op.add_column(
            tabelle,
            sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            op.f(f"fk_{tabelle}_geloescht_von_users"),
            tabelle,
            "users",
            ["geloescht_von"],
            ["id"],
        )

    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", f"role IN {ROLES_NEU}"
    )

    # Hoechstens ein aktiver loesch_operativ-Account je Mandant -- diese
    # Rolle sieht/bearbeitet fachliche Daten wie ein normaler Mitarbeiter
    # UND darf zusaetzlich loeschen/wiederherstellen, daher bewusst kein
    # Team, sondern eine einzelne verantwortliche Person. loesch_ansicht
    # (rein lesend) ist davon nicht betroffen, davon darf es beliebig viele
    # geben.
    op.create_index(
        op.f("uq_users_mandant_loesch_operativ_aktiv"),
        "users",
        ["mandant_id"],
        unique=True,
        postgresql_where=sa.text("role = 'loesch_operativ' AND aktiv = true"),
    )

    # fahrzeug_zuweisungen.user_id und inventurzyklen.lager_id waren bisher
    # schlicht eindeutig (hoechstens eine Zuweisung/ein Zyklus je Techniker/
    # Lagerort). Mit Soft-Delete wuerde ein weich geloeschter Datensatz den
    # Platz weiter belegen und eine Neuanlage fuer denselben Techniker/
    # Lagerort dauerhaft blockieren -- die Eindeutigkeit gilt daher ab jetzt
    # nur noch unter den aktiven (nicht geloeschten) Zeilen.
    op.drop_constraint("uq_fahrzeug_zuweisungen_user", "fahrzeug_zuweisungen", type_="unique")
    op.create_index(
        op.f("uq_fahrzeug_zuweisungen_user_aktiv"),
        "fahrzeug_zuweisungen",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("geloescht_am IS NULL"),
    )
    op.drop_constraint("uq_inventurzyklen_lager", "inventurzyklen", type_="unique")
    op.create_index(
        op.f("uq_inventurzyklen_lager_aktiv"),
        "inventurzyklen",
        ["lager_id"],
        unique=True,
        postgresql_where=sa.text("geloescht_am IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(op.f("uq_inventurzyklen_lager_aktiv"), table_name="inventurzyklen")
    op.create_unique_constraint("uq_inventurzyklen_lager", "inventurzyklen", ["lager_id"])
    op.drop_index(op.f("uq_fahrzeug_zuweisungen_user_aktiv"), table_name="fahrzeug_zuweisungen")
    op.create_unique_constraint(
        "uq_fahrzeug_zuweisungen_user", "fahrzeug_zuweisungen", ["user_id"]
    )

    op.drop_index(op.f("uq_users_mandant_loesch_operativ_aktiv"), table_name="users")

    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('super_admin', 'mandant_admin', 'disponent', 'techniker', "
        "'controller', 'mitarbeiter')",
    )

    for tabelle in reversed(_TABELLEN):
        op.drop_constraint(
            op.f(f"fk_{tabelle}_geloescht_von_users"), tabelle, type_="foreignkey"
        )
        op.drop_column(tabelle, "geloescht_von")
        op.drop_column(tabelle, "geloescht_am")
