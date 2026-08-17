"""Plattformweite Integrationen (aktuell nur SMTP): ein globaler
Mailversand als Fallback, wenn ein Mandant (noch) keine eigene
smtp-Integration hinterlegt hat (siehe app/services/email_service.py).
Bislang war das nur ueber GLOBAL_SMTP_*-Umgebungsvariablen konfigurierbar
(Server-Neustart noetig); jetzt pflegt ein super_admin das ueber eine
eigene Super-Admin-Seite, ohne Deployment-Zugriff.

RLS hier bewusst zweigeteilt (zwei Policies statt der ueblichen einen
mandant_isolation-Policy): SELECT ist fuer jede Session offen (jeder
Mandant braucht das als Fallback beim Mailversand lesen zu koennen,
nicht nur super_admin-Sessions), INSERT/UPDATE/DELETE bleibt exklusiv
super_admin vorbehalten. Postgres kombiniert mehrere permissive Policies
mit OR, das FOR SELECT USING(true) oeffnet also nur genau das Lesen,
waehrend FOR ALL weiterhin fuer Schreiboperationen greift.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064"
down_revision: Union[str, None] = "0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plattform_integrationen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secret_ref", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("typ IN ('smtp')", name="ck_plattform_integrationen_typ_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_plattform_integrationen_updated_at BEFORE UPDATE ON plattform_integrationen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE plattform_integrationen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE plattform_integrationen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY plattform_integrationen_lesbar ON plattform_integrationen
        FOR SELECT
        USING (true)
        """
    )
    op.execute(
        """
        CREATE POLICY plattform_integrationen_schreibbar ON plattform_integrationen
        FOR ALL
        USING (
          coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """
    )


def downgrade() -> None:
    op.drop_table("plattform_integrationen")
