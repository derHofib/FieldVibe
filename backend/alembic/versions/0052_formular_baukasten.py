"""Formular-Baukasten: Formular-Vorlagen mit frei zusammenstellbaren
Feldern, Zuordnung zu Auftragstypen (Leistungstyp) und Ausfuellungen an
Vorgaengen. Ausserdem: neuer VorgangEvent-Typ "formular" und neuer
Rechte-Bereich "formulare".

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEISTUNGSTYPEN = ("installation", "pruefung", "wartung", "stoerung", "beratung", "planung")


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
    # --- formulare -----------------------------------------------------
    op.create_table(
        "formulare",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_formulare_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_formulare_erstellt_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_formulare_updated_at BEFORE UPDATE ON formulare "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_formulare_mandant_id", "formulare", ["mandant_id"])
    _enable_rls("formulare")

    # --- formularfelder --------------------------------------------------
    op.create_table(
        "formularfelder",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formular_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feld_typ", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("hilfetext", sa.Text(), nullable=True),
        sa.Column("pflichtfeld", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("optionen", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_formularfelder_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["formular_id"], ["formulare.id"], name="fk_formularfelder_formular_id_formulare", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "feld_typ IN ('text', 'textarea', 'zahl', 'datum', 'dropdown', 'mehrfachauswahl', "
            "'ja_nein', 'bewertung', 'foto', 'unterschrift', 'gps', 'qr_scan', 'abschnitt')",
            name="ck_formularfelder_feld_typ_valid",
        ),
    )
    op.create_index("ix_formularfelder_mandant_id", "formularfelder", ["mandant_id"])
    op.create_index("ix_formularfelder_formular_id", "formularfelder", ["formular_id"])
    _enable_rls("formularfelder")

    # --- formular_auftragstyp_zuordnungen --------------------------------
    op.create_table(
        "formular_auftragstyp_zuordnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formular_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leistungstyp", sa.Text(), nullable=False),
        sa.Column("pflicht_vor_abschluss", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_formular_auftragstyp_zuordnungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["formular_id"],
            ["formulare.id"],
            name="fk_formular_auftragstyp_zuordnungen_formular_id_formulare",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "formular_id", "leistungstyp", name=op.f("uq_formular_auftragstyp_zuordnungen_formular_id")
        ),
        sa.CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}",
            name="ck_formular_auftragstyp_zuordnungen_leistungstyp_valid",
        ),
    )
    op.create_index(
        "ix_formular_auftragstyp_zuordnungen_mandant_id", "formular_auftragstyp_zuordnungen", ["mandant_id"]
    )
    _enable_rls("formular_auftragstyp_zuordnungen")

    # --- vorgang_formulare -------------------------------------------------
    op.create_table(
        "vorgang_formulare",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formular_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formular_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("antworten", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("ausgefuellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kundensichtbar", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("abgeschlossen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vorgang_formulare_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_vorgang_formulare_vorgang_id_vorgaenge", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["formular_id"], ["formulare.id"], name="fk_vorgang_formulare_formular_id_formulare"),
        sa.ForeignKeyConstraint(
            ["ausgefuellt_von"], ["users.id"], name="fk_vorgang_formulare_ausgefuellt_von_users"
        ),
        sa.CheckConstraint(
            "status IN ('offen', 'abgeschlossen')", name="ck_vorgang_formulare_status_valid"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_vorgang_formulare_updated_at BEFORE UPDATE ON vorgang_formulare "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_vorgang_formulare_mandant_id", "vorgang_formulare", ["mandant_id"])
    op.create_index("ix_vorgang_formulare_vorgang_id", "vorgang_formulare", ["vorgang_id"])
    _enable_rls("vorgang_formulare")

    # --- vorgang_events: neuer Typ "formular" -----------------------------
    op.execute("ALTER TABLE vorgang_events DROP CONSTRAINT ck_vorgang_events_event_type_valid")
    op.execute(
        "ALTER TABLE vorgang_events ADD CONSTRAINT ck_vorgang_events_event_type_valid "
        "CHECK (event_type IN ('kommentar', 'status_change', 'foto', 'dokument', 'mangel', "
        "'angebot', 'material', 'zeit_start', 'zeit_stop', 'termin', 'rechnung_status', "
        "'system', 'unterschrift', 'eingangsrechnung_status', 'formular'))"
    )

    # --- account_typ_rechte: neuer Bereich "formulare" --------------------
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung', 'formulare'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute("DELETE FROM account_typ_rechte WHERE bereich = 'formulare'")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung'))"
    )

    op.execute("ALTER TABLE vorgang_events DROP CONSTRAINT ck_vorgang_events_event_type_valid")
    op.execute("DELETE FROM vorgang_events WHERE event_type = 'formular'")
    op.execute(
        "ALTER TABLE vorgang_events ADD CONSTRAINT ck_vorgang_events_event_type_valid "
        "CHECK (event_type IN ('kommentar', 'status_change', 'foto', 'dokument', 'mangel', "
        "'angebot', 'material', 'zeit_start', 'zeit_stop', 'termin', 'rechnung_status', "
        "'system', 'unterschrift', 'eingangsrechnung_status'))"
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vorgang_formulare")
    op.drop_table("vorgang_formulare")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formular_auftragstyp_zuordnungen")
    op.drop_table("formular_auftragstyp_zuordnungen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formularfelder")
    op.drop_table("formularfelder")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formulare")
    op.drop_table("formulare")
