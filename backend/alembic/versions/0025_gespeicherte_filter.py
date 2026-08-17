"""Gespeicherte Filter-Vorlagen: personenbezogene, benannte Filter-Sets fuer
die Listenansichten (Aufträge/Vorgänge, Assets/Anlagen, Kunden, Standorte),
mit optionalem Standard-Flag je Nutzer und Entitaet.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
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
        "gespeicherte_filter",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitaet", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("filter_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ist_standard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_gespeicherte_filter_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_gespeicherte_filter_user_id_users"),
        sa.UniqueConstraint(
            "user_id", "entitaet", "name", name=op.f("uq_gespeicherte_filter_user_entitaet_name")
        ),
        sa.CheckConstraint(
            "entitaet IN ('vorgaenge', 'anlagen', 'kunden', 'standorte')",
            name=op.f("ck_gespeicherte_filter_entitaet_valid"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_gespeicherte_filter_updated_at BEFORE UPDATE ON gespeicherte_filter "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_gespeicherte_filter_mandant_id", "gespeicherte_filter", ["mandant_id"])
    op.create_index("ix_gespeicherte_filter_user_id", "gespeicherte_filter", ["user_id"])
    _enable_rls("gespeicherte_filter")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON gespeicherte_filter")
    op.drop_table("gespeicherte_filter")
