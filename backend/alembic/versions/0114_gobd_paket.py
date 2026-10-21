"""GoBD-Paket: Mandanten-Audit-Log (append-only, Hash-Kette), Festschreibung,
Aufbewahrung, Purge-Aufraeumliste, Mandanten-Vollexport.

Audit: audit_log wird erweitert statt dupliziert (akteur_typ, request_id, ip,
legacy) und per Trigger append-only (UPDATE/DELETE verboten, auch fuer den
Tabellenbesitzer; TRUNCATE bleibt fuer Test-Cleanup moeglich). Die
Hash-Verkettung steht bewusst in einer eigenen, ebenfalls append-only Tabelle
audit_log_siegel: die Eintraege selbst muessen nie nachtraeglich veraendert
werden, das Siegel entsteht erst kurz vor dem COMMIT (Advisory-Lock je Mandant
nur dort). Zeilen, die vor dieser Migration existierten, sind legacy und ohne
Siegel.

Downgrade ist verlustbehaftet: Siegel und neue Spalten gehen verloren.

Revision ID: 0114
Revises: 0113
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0114"
down_revision: Union[str, None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AKTEUR_TYPEN = ("user", "portal", "system", "partner")


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


def _append_only(table: str) -> None:
    funktion = f"{table}_append_only"
    op.execute(
        f"""
        CREATE FUNCTION {funktion}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION '{table} ist append-only (% nicht erlaubt)', TG_OP
            USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_append_only
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {funktion}()
        """
    )


def _append_only_entfernen(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only()")


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    # --- Audit ---------------------------------------------------------
    op.add_column(
        "audit_log",
        sa.Column("akteur_typ", sa.Text(), nullable=False, server_default="user"),
    )
    op.add_column("audit_log", sa.Column("request_id", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("ip", sa.Text(), nullable=True))
    op.add_column(
        "audit_log", sa.Column("legacy", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    # Altbestand: ohne Siegel, Akteur nur anhand actor_user_id ableitbar. Muss
    # vor dem Append-only-Trigger passieren.
    op.execute("UPDATE audit_log SET legacy = true")
    op.execute("UPDATE audit_log SET akteur_typ = 'system' WHERE actor_user_id IS NULL")
    op.create_check_constraint(
        op.f("ck_audit_log_akteur_typ_valid"), "audit_log", f"akteur_typ IN {_AKTEUR_TYPEN}"
    )
    op.create_index("ix_audit_log_mandant_id_created_at", "audit_log", ["mandant_id", "created_at"])
    _append_only("audit_log")

    op.create_table(
        "audit_log_siegel",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("audit_log_id", sa.BigInteger(), nullable=False),
        sa.Column("vorgaenger_hash", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_audit_log_siegel_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["audit_log_id"], ["audit_log.id"], name="fk_audit_log_siegel_audit_log_id_audit_log"),
        sa.UniqueConstraint("mandant_id", "seq", name="uq_audit_log_siegel_mandant_id_seq"),
        sa.UniqueConstraint("audit_log_id", name="uq_audit_log_siegel_audit_log_id"),
        sa.CheckConstraint("char_length(hash) = 64 AND char_length(vorgaenger_hash) = 64", name=op.f("ck_audit_log_siegel_hash_laenge")),
    )
    _enable_rls("audit_log_siegel")
    _append_only("audit_log_siegel")


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    _append_only_entfernen("audit_log_siegel")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON audit_log_siegel")
    op.drop_table("audit_log_siegel")

    _append_only_entfernen("audit_log")
    op.drop_index("ix_audit_log_mandant_id_created_at", table_name="audit_log")
    op.drop_constraint(op.f("ck_audit_log_akteur_typ_valid"), "audit_log", type_="check")
    op.drop_column("audit_log", "legacy")
    op.drop_column("audit_log", "ip")
    op.drop_column("audit_log", "request_id")
    op.drop_column("audit_log", "akteur_typ")
