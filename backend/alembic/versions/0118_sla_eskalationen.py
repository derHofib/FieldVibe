"""SLA-Eskalationsprotokoll (docs/konzepte/SLA.md, Phase 4).

Additive Tabelle: eine Zeile je (Vorgang, Stufe) ist zugleich die Idempotenz des
Workers (Unique) und die Revisionsspur, wann wen gewarnt wurde.

Revision ID: 0118
Revises: 0117
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0118"
down_revision: Union[str, None] = "0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.create_table(
        "sla_eskalationen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stufe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fortschritt_prozent", sa.Integer(), nullable=False),
        sa.Column("empfaenger_anzahl", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ausgeloest_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_sla_eskalationen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_sla_eskalationen_vorgang_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stufe_id"], ["sla_eskalationsstufen.id"], name="fk_sla_eskalationen_stufe_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("vorgang_id", "stufe_id", name="uq_sla_eskalationen_vorgang_stufe"),
    )
    op.execute("ALTER TABLE sla_eskalationen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sla_eskalationen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON sla_eskalationen
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
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_table("sla_eskalationen")
