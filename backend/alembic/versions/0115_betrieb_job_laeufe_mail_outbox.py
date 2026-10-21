"""Betrieb: job_laeufe (Zustand und Heartbeats der Hintergrundjobs) und
mail_outbox (Mail-Warteschlange mit Retry), email_log bekommt den Status
"ausstehend".

job_laeufe haelt je (job, mandant_id) den Zeitpunkt des letzten erfolgreichen
Laufs -- daraus berechnet der Worker, was faellig ist und nachgeholt werden muss.
Zeilen ohne mandant_id sind systemweite Jobs/Heartbeats (worker_tick, mail_sync).
Zugriff nur ueber system_session; RLS trotzdem nach Repo-Konvention.

mail_outbox: Versand erst nach dem Commit der ausloesenden Transaktion durch den
Worker; Anhaenge liegen im Objektspeicher (anhaenge[].s3_key).

Downgrade verwirft beide Tabellen samt offenen Mails; ausstehende email_log-
Eintraege werden vorher auf "fehler" gesetzt.

Revision ID: 0115
Revises: 0113
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0115"
# Bei Zusammenfuehrung mit der GoBD/Audit-Migration 0114 auf "0114" umhaengen.
down_revision: Union[str, None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OUTBOX_STATUS = ("pending", "sending", "sent", "failed")


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
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.create_table(
        "job_laeufe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("letzter_versuch_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("letzter_lauf_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("letzter_fehler", sa.Text(), nullable=True),
        sa.Column("fehler_in_folge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ergebnis", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_job_laeufe_mandant_id_mandanten", ondelete="CASCADE"
        ),
    )
    # Zwei partielle Indizes statt NULLS NOT DISTINCT: tragen auch das
    # ON CONFLICT der Upserts (je Variante eine Konfliktbedingung).
    op.create_index(
        "uq_job_laeufe_job_mandant", "job_laeufe", ["job", "mandant_id"],
        unique=True, postgresql_where=sa.text("mandant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_job_laeufe_job_system", "job_laeufe", ["job"],
        unique=True, postgresql_where=sa.text("mandant_id IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_job_laeufe_updated_at BEFORE UPDATE ON job_laeufe "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("job_laeufe")

    op.create_table(
        "mail_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("empfaenger", sa.Text(), nullable=False),
        sa.Column("betreff", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("anhaenge", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("versuche", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("naechster_versuch_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sending_seit", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("letzter_fehler", sa.Text(), nullable=True),
        sa.Column("gesendet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mail_outbox_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["email_log_id"], ["email_log.id"], name="fk_mail_outbox_email_log_id_email_log", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_mail_outbox_erstellt_von_users", ondelete="SET NULL"),
        sa.CheckConstraint(f"status IN {_OUTBOX_STATUS}", name=op.f("ck_mail_outbox_status_valid")),
    )
    # Der Worker sucht nur faellige pending-Zeilen; failed/sent sind selten
    # abgefragt und bleiben ausserhalb des Index.
    op.create_index(
        "ix_mail_outbox_faellig", "mail_outbox", ["naechster_versuch_am"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_mail_outbox_mandant_id_status", "mail_outbox", ["mandant_id", "status"])
    op.execute(
        "CREATE TRIGGER trg_mail_outbox_updated_at BEFORE UPDATE ON mail_outbox "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("mail_outbox")

    op.drop_constraint(op.f("ck_email_log_status_valid"), "email_log", type_="check")
    op.create_check_constraint(
        op.f("ck_email_log_status_valid"), "email_log", "status IN ('gesendet', 'fehler', 'ausstehend')"
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.execute("UPDATE email_log SET status = 'fehler', fehlermeldung = coalesce(fehlermeldung, 'Abgebrochen (Downgrade)') WHERE status = 'ausstehend'")
    op.drop_constraint(op.f("ck_email_log_status_valid"), "email_log", type_="check")
    op.create_check_constraint(op.f("ck_email_log_status_valid"), "email_log", "status IN ('gesendet', 'fehler')")
    op.drop_table("mail_outbox")
    op.drop_table("job_laeufe")
