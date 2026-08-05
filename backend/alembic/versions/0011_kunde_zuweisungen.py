"""Nacharbeit: Kunde-Techniker-Zuweisungen (Techniker sehen nur zugewiesene Kunden)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kunde_zuweisungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_kunde_zuweisungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["kunde_id"], ["kunden.id"], name="fk_kunde_zuweisungen_kunde_id_kunden", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_kunde_zuweisungen_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("kunde_id", "user_id", name="uq_kunde_zuweisungen_kunde_user"),
    )
    op.create_index("ix_kunde_zuweisungen_mandant_id", "kunde_zuweisungen", ["mandant_id"])
    op.create_index("ix_kunde_zuweisungen_kunde_id", "kunde_zuweisungen", ["kunde_id"])
    op.create_index("ix_kunde_zuweisungen_user_id", "kunde_zuweisungen", ["user_id"])

    op.execute("ALTER TABLE kunde_zuweisungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE kunde_zuweisungen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON kunde_zuweisungen
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


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON kunde_zuweisungen")
    op.drop_table("kunde_zuweisungen")
