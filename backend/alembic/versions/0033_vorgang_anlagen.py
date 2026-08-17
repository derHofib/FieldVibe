"""Vorgang-Anlagen: weitere Anlagen an einem Vorgang zusaetzlich zur
einzelnen Vorgang.anlage_id (der "Haupt-Anlage") -- v.a. damit beim
Anlegen ueber einen Standort mehrere Anlagen automatisch mit in den
Vorgang uebernommen werden koennen.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
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
        "vorgang_anlagen",
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_vorgang_anlagen_vorgang_id_vorgaenge", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["anlage_id"], ["anlagen.id"], name="fk_vorgang_anlagen_anlage_id_anlagen", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_vorgang_anlagen_mandant_id_mandanten"
        ),
    )
    op.create_index("ix_vorgang_anlagen_mandant_id", "vorgang_anlagen", ["mandant_id"])
    op.create_index("ix_vorgang_anlagen_anlage_id", "vorgang_anlagen", ["anlage_id"])
    _enable_rls("vorgang_anlagen")


def downgrade() -> None:
    op.drop_table("vorgang_anlagen")
