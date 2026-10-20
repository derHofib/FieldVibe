"""Datenimport (CSV/XLSX-Assistent): import_laeufe und import_lauf_eintraege.

import_laeufe ist der Nachweis je Import (Datei-Hash, Zaehler, Zuordnung, Optionen);
die hochgeladene Quelldatei liegt solange im Objektspeicher (object_key) und wird
nach Abschluss bzw. 24 h aufgeraeumt. import_lauf_eintraege haelt die IDs der durch
einen Lauf angelegten/aktualisierten Datensaetze -- Grundlage fuer "Import
rueckgaengig" (Papierkorb), ohne die Fachtabellen um eine Spalte zu erweitern.

Downgrade ist verlustbehaftet: der Nachweis und die Rueckgaengig-Zuordnung gehen
verloren, die importierten Datensaetze selbst bleiben unveraendert.

Revision ID: 0113
Revises: 0111
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0113"
# Bei Zusammenfuehrung mit der Sicherheits-Migration 0112 auf "0112" umhaengen.
down_revision: Union[str, None] = "0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENTITAETEN = ("kunden", "anlagen", "material")
_STATUS = ("analysiert", "geprueft", "abgeschlossen", "abgebrochen", "rueckgaengig", "abgelaufen")
_EINTRAG_TYPEN = ("kunde", "standort", "anlage", "pruefzyklus", "material")
_EINTRAG_AKTIONEN = ("angelegt", "aktualisiert")


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
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.create_table(
        "import_laeufe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitaet", sa.Text(), nullable=False),
        sa.Column("dateiname", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("dateigroesse", sa.Integer(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("trennzeichen", sa.Text(), nullable=True),
        sa.Column("kodierung", sa.Text(), nullable=True),
        sa.Column("blatt", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="analysiert"),
        sa.Column("zeilen_gesamt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zeilen_neu", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zeilen_aktualisiert", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zeilen_uebersprungen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zeilen_fehler", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zeilen_warnungen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spalten", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("mapping", postgresql.JSONB(), nullable=True),
        sa.Column("optionen", postgresql.JSONB(), nullable=True),
        sa.Column("konfig_hash", sa.Text(), nullable=True),
        sa.Column("ergebnis", postgresql.JSONB(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("fehlerbericht_key", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geprueft_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ausgefuehrt_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abgeschlossen_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rueckgaengig_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_import_laeufe_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_import_laeufe_erstellt_von_users"),
        sa.CheckConstraint(f"entitaet IN {_ENTITAETEN}", name=op.f("ck_import_laeufe_entitaet_valid")),
        sa.CheckConstraint(f"status IN {_STATUS}", name=op.f("ck_import_laeufe_status_valid")),
        sa.CheckConstraint("format IN ('csv', 'xlsx')", name=op.f("ck_import_laeufe_format_valid")),
    )
    op.create_index("ix_import_laeufe_mandant_id_created_at", "import_laeufe", ["mandant_id", "created_at"])
    op.execute(
        "CREATE TRIGGER trg_import_laeufe_updated_at BEFORE UPDATE ON import_laeufe "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("import_laeufe")

    op.create_table(
        "import_lauf_eintraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_lauf_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitaet_typ", sa.Text(), nullable=False),
        sa.Column("entitaet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("zeile", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_import_lauf_eintraege_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["import_lauf_id"],
            ["import_laeufe.id"],
            name="fk_import_lauf_eintraege_import_lauf_id_import_laeufe",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"entitaet_typ IN {_EINTRAG_TYPEN}", name=op.f("ck_import_lauf_eintraege_typ_valid")),
        sa.CheckConstraint(f"aktion IN {_EINTRAG_AKTIONEN}", name=op.f("ck_import_lauf_eintraege_aktion_valid")),
    )
    op.create_index("ix_import_lauf_eintraege_import_lauf_id", "import_lauf_eintraege", ["import_lauf_id"])
    op.create_index("ix_import_lauf_eintraege_mandant_id", "import_lauf_eintraege", ["mandant_id"])
    _enable_rls("import_lauf_eintraege")


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON import_lauf_eintraege")
    op.drop_table("import_lauf_eintraege")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON import_laeufe")
    op.drop_table("import_laeufe")
