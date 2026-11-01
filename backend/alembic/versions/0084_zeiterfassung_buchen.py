"""Zeiterfassung Stufe 2 (docs/konzepte/ZEITERFASSUNG.md): Buchungsablauf.

Erfasste Zeit ist zunaechst nur "vermerkt". Abrechenbar wird sie erst nach
aktiver Buchung durch einen Nutzer mit dem neuen Einzelrecht "Zeiten
buchen" (account_typen.darf_zeiten_buchen). Jeder Uebergang landet im
Protokoll zeiterfassung_aenderungen.

Altbestand (Konzept 5.1, mit dem Nutzer abgestimmt): Eintraege an
Vorgaengen mit Status 'abgerechnet' werden zu buchungsstatus='abgerechnet',
alle uebrigen Eintraege MIT Vorgang zu 'gebucht' (damit laufende
Abrechnungen am Umstellungstag nicht ohne Zeitvorschlaege dastehen).
Eintraege OHNE Vorgang (Urlaub, Krankheit, ...) bleiben beim Spalten-
Default 'vermerkt' -- fuer sie ist Buchen ohnehin nie moeglich.

Revision ID: 0084
Revises: 0083
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """
    )


def upgrade() -> None:
    op.add_column(
        "zeiterfassung",
        sa.Column("buchungsstatus", sa.Text(), nullable=False, server_default="vermerkt"),
    )
    # Bares Suffix (kein "ck_zeiterfassung_"-Praefix): create_check_constraint
    # wendet die naming_convention (app/db/base.py) auf den Namen an -- ein
    # bereits praefigierter Name wuerde doppelt praefigiert (siehe Docstring
    # in Migration 0076 zur selben Falle).
    op.create_check_constraint(
        "buchungsstatus_valid",
        "zeiterfassung",
        "buchungsstatus IN ('vermerkt', 'vorgemerkt', 'gebucht', 'abgerechnet')",
    )
    op.add_column(
        "zeiterfassung", sa.Column("vorgemerkt_von", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "zeiterfassung", sa.Column("vorgemerkt_am", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "zeiterfassung", sa.Column("gebucht_von", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("zeiterfassung", sa.Column("gebucht_am", sa.DateTime(timezone=True), nullable=True))
    op.add_column("zeiterfassung", sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "zeiterfassung", sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_zeiterfassung_vorgemerkt_von_users", "zeiterfassung", "users", ["vorgemerkt_von"], ["id"]
    )
    op.create_foreign_key(
        "fk_zeiterfassung_gebucht_von_users", "zeiterfassung", "users", ["gebucht_von"], ["id"]
    )
    op.create_foreign_key(
        "fk_zeiterfassung_geloescht_von_users", "zeiterfassung", "users", ["geloescht_von"], ["id"]
    )

    # Altbestand: siehe Docstring oben. Das Backfill laeuft als Systemquery
    # ohne RLS-Kontext (Migrationen laufen ausserhalb der App), betrifft
    # also bewusst alle Mandanten in einem Schritt.
    op.execute(
        """
        UPDATE zeiterfassung z
        SET buchungsstatus = 'abgerechnet'
        FROM vorgaenge v
        WHERE z.vorgang_id = v.id AND v.status = 'abgerechnet'
        """
    )
    op.execute(
        """
        UPDATE zeiterfassung z
        SET buchungsstatus = 'gebucht'
        FROM vorgaenge v
        WHERE z.vorgang_id = v.id AND v.status != 'abgerechnet'
        """
    )

    op.add_column(
        "account_typen",
        sa.Column("darf_zeiten_buchen", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "zeiterfassung_aenderungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zeiterfassung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("feld", sa.Text(), nullable=True),
        sa.Column("alter_wert", postgresql.JSONB(), nullable=True),
        sa.Column("neuer_wert", postgresql.JSONB(), nullable=True),
        sa.Column("grund", sa.Text(), nullable=True),
        sa.Column("geaendert_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geaendert_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_zeiterfassung_aenderungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["zeiterfassung_id"],
            ["zeiterfassung.id"],
            name="fk_zeiterfassung_aenderungen_zeiterfassung_id_zeiterfassung",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["geaendert_von"], ["users.id"], name="fk_zeiterfassung_aenderungen_geaendert_von_users"
        ),
        sa.CheckConstraint(
            "aktion IN ('angelegt', 'geaendert', 'geloescht', 'wiederhergestellt', 'vorgemerkt', "
            "'vormerkung_zurueckgezogen', 'gebucht', 'buchung_storniert', 'abgerechnet')",
            name="ck_zeiterfassung_aenderungen_aktion_valid",
        ),
    )
    op.create_index(
        "ix_zeiterfassung_aenderungen_mandant_id", "zeiterfassung_aenderungen", ["mandant_id"]
    )
    op.create_index(
        "ix_zeiterfassung_aenderungen_zeiterfassung_id",
        "zeiterfassung_aenderungen",
        ["zeiterfassung_id"],
    )
    _enable_rls("zeiterfassung_aenderungen")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON zeiterfassung_aenderungen")
    op.drop_table("zeiterfassung_aenderungen")

    op.drop_column("account_typen", "darf_zeiten_buchen")

    op.drop_constraint("fk_zeiterfassung_geloescht_von_users", "zeiterfassung", type_="foreignkey")
    op.drop_constraint("fk_zeiterfassung_gebucht_von_users", "zeiterfassung", type_="foreignkey")
    op.drop_constraint("fk_zeiterfassung_vorgemerkt_von_users", "zeiterfassung", type_="foreignkey")
    op.drop_column("zeiterfassung", "geloescht_von")
    op.drop_column("zeiterfassung", "geloescht_am")
    op.drop_column("zeiterfassung", "gebucht_am")
    op.drop_column("zeiterfassung", "gebucht_von")
    op.drop_column("zeiterfassung", "vorgemerkt_am")
    op.drop_column("zeiterfassung", "vorgemerkt_von")
    op.drop_constraint("buchungsstatus_valid", "zeiterfassung", type_="check")
    op.drop_column("zeiterfassung", "buchungsstatus")
