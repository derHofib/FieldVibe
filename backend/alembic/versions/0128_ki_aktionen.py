"""KI-Journal und Regeln-Grundgeruest (MCP-Ausbau Etappe A).

- ki_aktionen: jede Aktion, die ein KI-Assistent (MCP) im Namen eines Nutzers ausfuehrt, mit
  Vorher/Nachher, Rueckweg (Undo) und -- ab Etappe B -- dem eingefrorenen Vorschlag. Eigene
  Tabelle statt Audit-Log: das Audit-Log ist die unveraenderliche GoBD-Hash-Kette, das
  Rueckgaengig braucht strukturierte Werte und einen Status. Verknuepft ueber ki_aktion_id im
  Audit-Payload.
- ki_regeln: Modus und Tageslimit je Aktionsart und Mandant (Etappe B). Hier nur die Tabelle.

Beide Tabellen: RLS-Policy + FORCE nach Repo-Konvention; ki_aktionen zusaetzlich updated_at-Trigger.
Kein Backfill, alles ist neu.

Downgrade: beide Tabellen werden verworfen.

Revision ID: 0128
Revises: 0127
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0128"
down_revision: Union[str, None] = "0127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS = ("ausgefuehrt", "vorgeschlagen", "abgelehnt", "verfallen", "fehlgeschlagen", "rueckgaengig")
_MODI = ("direkt", "chat", "fieldvibe", "vier_augen", "aus")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        WITH CHECK (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        """
    )


def _json_liste(name: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"))


def upgrade() -> None:
    op.create_table(
        "ki_aktionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ki_verbindung_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("aktionsart", sa.Text(), nullable=False),
        sa.Column("stufe", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("zusammenfassung", sa.Text(), nullable=False),
        _json_liste("ziele"),
        _json_liste("aenderungen"),
        _json_liste("erzeugt"),
        _json_liste("rueckweg"),
        # Ab Etappe B: eingefrorener Vorschlag (Stufe 3). In Etappe A nur angelegt.
        sa.Column("eingabe", postgresql.JSONB(), nullable=True),
        sa.Column("vorschau", postgresql.JSONB(), nullable=True),
        sa.Column("inhalt_hash", sa.Text(), nullable=True),
        sa.Column("modus", sa.Text(), nullable=True),
        sa.Column("gueltig_bis", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("bestaetigt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bestaetigt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("bestaetigt_via", sa.Text(), nullable=True),
        sa.Column("rueckgaengig_bis", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rueckgaengig_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rueckgaengig_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fehler", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_ki_aktionen_mandant_id_mandanten", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ki_aktionen_user_id_users"),
        sa.ForeignKeyConstraint(
            ["ki_verbindung_id"], ["ki_verbindungen.id"],
            name="fk_ki_aktionen_ki_verbindung_id_ki_verbindungen", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["bestaetigt_von"], ["users.id"], name="fk_ki_aktionen_bestaetigt_von_users"),
        sa.ForeignKeyConstraint(["rueckgaengig_von"], ["users.id"], name="fk_ki_aktionen_rueckgaengig_von_users"),
        sa.CheckConstraint("stufe BETWEEN 1 AND 3", name="stufe_valid"),
        sa.CheckConstraint(f"status IN {_STATUS}", name="status_valid"),
    )
    op.create_index("ix_ki_aktionen_mandant_erstellt", "ki_aktionen", ["mandant_id", sa.text("erstellt_am DESC")])
    op.create_index(
        "ix_ki_aktionen_mandant_user_erstellt", "ki_aktionen", ["mandant_id", "user_id", sa.text("erstellt_am DESC")]
    )
    op.create_index(
        "ix_ki_aktionen_vorschlag_gueltig",
        "ki_aktionen",
        ["status", "gueltig_bis"],
        postgresql_where=sa.text("status = 'vorgeschlagen'"),
    )
    op.execute(
        "CREATE TRIGGER trg_ki_aktionen_updated_at BEFORE UPDATE ON ki_aktionen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("ki_aktionen")

    op.create_table(
        "ki_regeln",
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aktionsart", sa.Text(), nullable=False),
        sa.Column("modus", sa.Text(), nullable=False),
        sa.Column("tageslimit", sa.Integer(), nullable=True),
        sa.Column("geaendert_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geaendert_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("mandant_id", "aktionsart", name="pk_ki_regeln"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_ki_regeln_mandant_id_mandanten", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["geaendert_von"], ["users.id"], name="fk_ki_regeln_geaendert_von_users"),
        sa.CheckConstraint(f"modus IN {_MODI}", name="modus_valid"),
        sa.CheckConstraint("tageslimit IS NULL OR tageslimit >= 0", name="tageslimit_nicht_negativ"),
    )
    _enable_rls("ki_regeln")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON ki_regeln")
    op.drop_table("ki_regeln")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON ki_aktionen")
    op.drop_table("ki_aktionen")
