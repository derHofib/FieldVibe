"""Persoenliche IMAP/SMTP-Postfaecher (mail_accounts): Stufe 1 des
FieldVibe-eigenen Mailclients, der Outlook & Co. fuer den einzelnen Nutzer
ersetzen soll. Nur die Kontoverwaltung -- Ordner/Nachrichten/Anhaenge
folgen in einer eigenen Migration, sobald die Sync-Engine steht.

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060"
down_revision: Union[str, None] = "0059"
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
        "mail_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email_adresse", sa.Text(), nullable=False),
        sa.Column("imap_host", sa.Text(), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_verschluesselung", sa.Text(), nullable=False, server_default="ssl"),
        sa.Column("imap_benutzername", sa.Text(), nullable=False),
        sa.Column("smtp_host", sa.Text(), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_verschluesselung", sa.Text(), nullable=False, server_default="starttls"),
        sa.Column("smtp_benutzername", sa.Text(), nullable=False),
        sa.Column("passwort_verschluesselt", sa.Text(), nullable=False),
        sa.Column("signatur", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("letzter_sync_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("letzter_sync_fehler", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mail_accounts_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mail_accounts_user_id_users"),
        sa.UniqueConstraint(
            "user_id", "email_adresse", name=op.f("uq_mail_accounts_user_email")
        ),
        sa.CheckConstraint(
            "imap_verschluesselung IN ('ssl', 'starttls', 'keine')",
            name=op.f("ck_mail_accounts_imap_verschluesselung_valid"),
        ),
        sa.CheckConstraint(
            "smtp_verschluesselung IN ('ssl', 'starttls', 'keine')",
            name=op.f("ck_mail_accounts_smtp_verschluesselung_valid"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_mail_accounts_updated_at BEFORE UPDATE ON mail_accounts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_mail_accounts_mandant_id", "mail_accounts", ["mandant_id"])
    op.create_index("ix_mail_accounts_user_id", "mail_accounts", ["user_id"])
    _enable_rls("mail_accounts")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mail_accounts")
    op.drop_table("mail_accounts")
