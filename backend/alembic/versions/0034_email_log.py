"""E-Mail-Versand: Protokoll aller aus FieldVibe heraus versendeten
E-Mails (Kunde/Vorgang-Freitext, Angebot/Rechnung/Bestellung als PDF).

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: Union[str, None] = "0033"
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
        "email_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("empfaenger", sa.Text(), nullable=False),
        sa.Column("betreff", sa.Text(), nullable=False),
        sa.Column("inhalt", sa.Text(), nullable=False),
        sa.Column("anhang_dateiname", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("fehlermeldung", sa.Text(), nullable=True),
        sa.Column("gesendet_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_email_log_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["gesendet_von"], ["users.id"], name="fk_email_log_gesendet_von_users"),
        sa.CheckConstraint(
            "entity_type IN ('kunde', 'vorgang', 'angebot', 'rechnung', 'bestellung')",
            name=op.f("ck_email_log_entity_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('gesendet', 'fehler')", name=op.f("ck_email_log_status_valid")
        ),
    )
    op.create_index("ix_email_log_mandant_id", "email_log", ["mandant_id"])
    op.create_index("ix_email_log_entity", "email_log", ["entity_type", "entity_id"])
    _enable_rls("email_log")


def downgrade() -> None:
    op.drop_table("email_log")
