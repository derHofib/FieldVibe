"""Kennzahlen-Dashboards (Konzept kennzahlen-dashboards, Etappe A+B).

Je Nutzer benannte Dashboards (Layout als JSONB); optional fuer alle Nutzer des
Mandanten sichtbar (fuer_alle, nur vom Admin setzbar). `vorlage` merkt sich den
Schluessel der Systemvorlage, aus der kopiert wurde.

- kennzahlen_dashboards: RLS-Policy + FORCE + updated_at-Trigger nach Repo-Konvention.
- user_id mit ON DELETE CASCADE: Dashboards gehoeren der Person, nicht dem Mandanten.

Revision ID: 0123
Revises: 0121
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0123"
down_revision: Union[str, None] = "0121"
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
        "kennzahlen_dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("layout", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fuer_alle", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vorlage", sa.Text(), nullable=True),
        sa.Column("sortierung", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_kennzahlen_dashboards_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_kennzahlen_dashboards_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_kennzahlen_dashboards_user_name"),
    )
    op.create_index("ix_kennzahlen_dashboards_mandant_user", "kennzahlen_dashboards", ["mandant_id", "user_id"])
    op.execute(
        "CREATE TRIGGER trg_kennzahlen_dashboards_updated_at BEFORE UPDATE ON kennzahlen_dashboards "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("kennzahlen_dashboards")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON kennzahlen_dashboards")
    op.drop_table("kennzahlen_dashboards")
