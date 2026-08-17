"""Mail Stufe 2: Ordner/Nachrichten/Anhaenge fuer die IMAP-Sync-Engine
(mail_folders/mail_messages/mail_attachments) plus Volltextsuche
(search_vector) auf mail_messages nach demselben Muster wie
vorgaenge.search_vector (siehe 0003_social_ux.py).

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061"
down_revision: Union[str, None] = "0060"
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
        "mail_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mail_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("imap_name", sa.Text(), nullable=False),
        sa.Column("anzeigename", sa.Text(), nullable=False),
        sa.Column("uidvalidity", sa.BigInteger(), nullable=True),
        sa.Column("last_uid", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("letzter_sync_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sortierung", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mail_folders_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["mail_account_id"], ["mail_accounts.id"], name="fk_mail_folders_mail_account_id_mail_accounts",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "mail_account_id", "imap_name", name=op.f("uq_mail_folders_account_imap_name")
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_mail_folders_updated_at BEFORE UPDATE ON mail_folders "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_mail_folders_mandant_id", "mail_folders", ["mandant_id"])
    op.create_index("ix_mail_folders_mail_account_id", "mail_folders", ["mail_account_id"])
    _enable_rls("mail_folders")

    op.create_table(
        "mail_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mail_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("message_id_header", sa.Text(), nullable=True),
        sa.Column("in_reply_to", sa.Text(), nullable=True),
        sa.Column("references_header", sa.Text(), nullable=True),
        sa.Column("von_name", sa.Text(), nullable=True),
        sa.Column("von_adresse", sa.Text(), nullable=True),
        sa.Column("an", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cc", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("betreff", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("datum", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("gelesen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mail_messages_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["mail_account_id"], ["mail_accounts.id"], name="fk_mail_messages_mail_account_id_mail_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["mail_folders.id"], name="fk_mail_messages_folder_id_mail_folders",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("folder_id", "uid", name=op.f("uq_mail_messages_folder_uid")),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_mail_message_search_vector() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector(
            'german',
            coalesce(NEW.betreff, '') || ' ' || coalesce(NEW.body_text, '') || ' ' ||
            coalesce(NEW.von_name, '') || ' ' || coalesce(NEW.von_adresse, '')
          );
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_mail_messages_search_vector BEFORE INSERT OR UPDATE OF "
        "betreff, body_text, von_name, von_adresse ON mail_messages "
        "FOR EACH ROW EXECUTE FUNCTION set_mail_message_search_vector()"
    )
    op.alter_column("mail_messages", "search_vector", nullable=False, server_default=None)
    op.create_index(
        "ix_mail_messages_search_vector", "mail_messages", ["search_vector"], postgresql_using="gin"
    )
    op.execute(
        "CREATE TRIGGER trg_mail_messages_updated_at BEFORE UPDATE ON mail_messages "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_mail_messages_mandant_id", "mail_messages", ["mandant_id"])
    op.create_index("ix_mail_messages_mail_account_id", "mail_messages", ["mail_account_id"])
    op.create_index("ix_mail_messages_folder_id", "mail_messages", ["folder_id"])
    op.create_index("ix_mail_messages_datum", "mail_messages", ["datum"])
    _enable_rls("mail_messages")

    op.create_table(
        "mail_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dateiname", sa.Text(), nullable=False),
        sa.Column("mimetype", sa.Text(), nullable=False),
        sa.Column("groesse_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("eingebettet", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mail_attachments_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["mail_messages.id"], name="fk_mail_attachments_message_id_mail_messages",
            ondelete="CASCADE",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_mail_attachments_updated_at BEFORE UPDATE ON mail_attachments "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_mail_attachments_mandant_id", "mail_attachments", ["mandant_id"])
    op.create_index("ix_mail_attachments_message_id", "mail_attachments", ["message_id"])
    _enable_rls("mail_attachments")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mail_attachments")
    op.drop_table("mail_attachments")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mail_messages")
    op.execute("DROP TRIGGER IF EXISTS trg_mail_messages_search_vector ON mail_messages")
    op.execute("DROP FUNCTION IF EXISTS set_mail_message_search_vector()")
    op.drop_table("mail_messages")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mail_folders")
    op.drop_table("mail_folders")
