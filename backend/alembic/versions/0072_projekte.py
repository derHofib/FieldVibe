"""Projekte: Asana-artiges Kanban-Projektmanagement fuer die Office-
Oberflaeche. Ein Projekt hat frei benennbare/sortierbare Spalten
(projekt_spalten) und Aufgaben-Karten (projekt_aufgaben) mit Faelligkeit,
Prioritaet, Zustaendigem, Checkliste (JSONB, volles Ersetzen per PATCH wie
bei Board.inhalt_json) und optionaler Verknuepfung zu einem bestehenden
Vorgang (vorgang_id, nullable) -- rein referenziell, kein Status-Sync in
beide Richtungen (siehe app/api/routes/projekt_aufgaben.py).

Reihenfolge innerhalb einer Spalte kommt bewusst ohne eigenes position-Feld
aus (analog zum bestehenden Vorgaenge-Kanban, das ebenfalls nur nach Status
filtert statt manuell zu sortieren) -- Sortierung nach created_at.

projekt_spalten ist nicht papierkorbfaehig (wie nav_kategorien: reine
Konfiguration), projekt_aufgaben.spalte_id verweist mit ON DELETE RESTRICT
darauf, damit eine Spalte mit noch offenen Aufgaben nicht geloescht werden
kann.

Ergaenzt ausserdem "projekte" als neuen Rechte-Bereich in der
Account-Typen-Matrix (gleiches Muster wie Migration 0070 fuer "partner").

Revision ID: 0072
Revises: 0071
Create Date: 2026-08-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0072"
down_revision: Union[str, None] = "0071"
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
    op.create_table(
        "projekte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("archiviert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_projekte_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_projekte_erstellt_von_users"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_projekte_geloescht_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_projekte_updated_at BEFORE UPDATE "
        "ON projekte FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_projekte_mandant_id", "projekte", ["mandant_id"])
    _enable_rls("projekte")

    op.create_table(
        "projekt_spalten",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("reihenfolge", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_projekt_spalten_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["projekt_id"], ["projekte.id"], name="fk_projekt_spalten_projekt_id_projekte", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_projekt_spalten_mandant_id", "projekt_spalten", ["mandant_id"])
    op.create_index("ix_projekt_spalten_projekt_id", "projekt_spalten", ["projekt_id"])
    _enable_rls("projekt_spalten")

    op.create_table(
        "projekt_aufgaben",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("spalte_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("faelligkeit_am", sa.Date(), nullable=True),
        sa.Column("prioritaet", sa.Text(), nullable=False, server_default="mittel"),
        sa.Column("zugewiesen_an", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checkliste", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("zusatzfelder", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_projekt_aufgaben_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["projekt_id"], ["projekte.id"], name="fk_projekt_aufgaben_projekt_id_projekte", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["spalte_id"], ["projekt_spalten.id"], name="fk_projekt_aufgaben_spalte_id_projekt_spalten",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["zugewiesen_an"], ["users.id"], name="fk_projekt_aufgaben_zugewiesen_an_users"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_projekt_aufgaben_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_projekt_aufgaben_erstellt_von_users"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_projekt_aufgaben_geloescht_von_users"),
        sa.CheckConstraint(
            "prioritaet IN ('niedrig', 'mittel', 'hoch')", name="ck_projekt_aufgaben_prioritaet_valid"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_projekt_aufgaben_updated_at BEFORE UPDATE "
        "ON projekt_aufgaben FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_projekt_aufgaben_mandant_id", "projekt_aufgaben", ["mandant_id"])
    op.create_index("ix_projekt_aufgaben_projekt_id", "projekt_aufgaben", ["projekt_id"])
    op.create_index("ix_projekt_aufgaben_spalte_id", "projekt_aufgaben", ["spalte_id"])
    op.create_index("ix_projekt_aufgaben_vorgang_id", "projekt_aufgaben", ["vorgang_id"])
    _enable_rls("projekt_aufgaben")

    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung', 'formulare', 'partner', 'projekte'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute("DELETE FROM account_typ_rechte WHERE bereich = 'projekte'")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung', 'formulare', 'partner'))"
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON projekt_aufgaben")
    op.drop_table("projekt_aufgaben")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON projekt_spalten")
    op.drop_table("projekt_spalten")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON projekte")
    op.drop_table("projekte")
