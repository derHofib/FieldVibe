"""KI-Zugriff (MCP-Server): ki_clients, ki_verbindungen und Modul "ki_zugriff".

ki_clients haelt die per Dynamic Client Registration angelegten OAuth-Clients
(z. B. Claude). Bewusst ohne mandant_id und ohne RLS: die Registrierung passiert
vor jedem Login, es gibt keinen Mandanten-Kontext, und die Zeilen enthalten nur
Client-Metadaten (Name, Redirect-URIs), keine Mandantendaten.

ki_verbindungen ist je eine vom Nutzer erteilte Einwilligung (Nutzer + Client +
Scopes) und der Anker fuer Widerruf, Refresh-Rotation (refresh_jti) und die
Anzeige im Profil. RLS nach Repo-Konvention.

"ki_zugriff" wird wie "karten" (0048) opt-IN: bestehende Mandanten bekommen es in
deaktivierte_module nachgetragen. Die Policy auf mandanten kennt seit 0117 den
Super-Admin-Bypass nicht mehr -- der Backfill laeuft deshalb innerhalb von
rls_fuer_backfill_aufheben("mandanten") (app/db/migrations_helfer.py), das
FORCE ROW LEVEL SECURITY kurz aufhebt und in derselben Transaktion wieder setzt.

Revision ID: 0119
Revises: 0118
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.migrations_helfer import rls_fuer_backfill_aufheben

revision: str = "0119"
down_revision: Union[str, None] = "0118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    op.create_table(
        "ki_clients",
        sa.Column("client_id", sa.Text(), primary_key=True),
        sa.Column("client_info", postgresql.JSONB(), nullable=False),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "ki_verbindungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("code_eingeloest_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("refresh_jti", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("zuletzt_genutzt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("widerrufen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_ki_verbindungen_mandant_id_mandanten", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ki_verbindungen_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["client_id"], ["ki_clients.client_id"], name="fk_ki_verbindungen_client_id_ki_clients"
        ),
    )
    op.create_index("ix_ki_verbindungen_mandant_id", "ki_verbindungen", ["mandant_id"])
    op.create_index("ix_ki_verbindungen_user_id", "ki_verbindungen", ["user_id"])
    op.execute(
        "CREATE TRIGGER trg_ki_verbindungen_updated_at BEFORE UPDATE ON ki_verbindungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("ki_verbindungen")

    with rls_fuer_backfill_aufheben("mandanten"):
        op.execute(
            "UPDATE mandanten SET deaktivierte_module = deaktivierte_module || '[\"ki_zugriff\"]'::jsonb "
            "WHERE NOT deaktivierte_module @> '[\"ki_zugriff\"]'::jsonb"
        )


def downgrade() -> None:
    with rls_fuer_backfill_aufheben("mandanten"):
        op.execute("UPDATE mandanten SET deaktivierte_module = deaktivierte_module - 'ki_zugriff'")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON ki_verbindungen")
    op.drop_table("ki_verbindungen")
    op.drop_table("ki_clients")
