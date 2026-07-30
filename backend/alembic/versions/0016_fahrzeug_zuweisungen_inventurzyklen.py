"""Techniker-Fahrzeug-Zuweisung (Standard-Lagerort-Vorschlag) und
Inventurzyklen je Lagerort (analog zu Pruefzyklen, aber ohne Vorgang-
Erzeugung -- eine Inventur ist kein Kundenauftrag). aktiv=False
deaktiviert/pausiert einen Inventurzyklus vollstaendig.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _mandant_isolation_policy(table: str) -> str:
    return f"""
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


def upgrade() -> None:
    # --- fahrzeug_zuweisungen ------------------------------------------------
    op.create_table(
        "fahrzeug_zuweisungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_fahrzeug_zuweisungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_fahrzeug_zuweisungen_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_fahrzeug_zuweisungen_anlage_id_anlagen"),
        sa.UniqueConstraint("user_id", name="uq_fahrzeug_zuweisungen_user"),
    )
    op.execute(
        "CREATE TRIGGER trg_fahrzeug_zuweisungen_updated_at BEFORE UPDATE ON fahrzeug_zuweisungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_fahrzeug_zuweisungen_mandant_id", "fahrzeug_zuweisungen", ["mandant_id"])
    op.create_index("ix_fahrzeug_zuweisungen_anlage_id", "fahrzeug_zuweisungen", ["anlage_id"])

    op.execute("ALTER TABLE fahrzeug_zuweisungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fahrzeug_zuweisungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("fahrzeug_zuweisungen"))

    # --- inventurzyklen -------------------------------------------------------
    op.create_table(
        "inventurzyklen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lager_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intervall_tage", sa.SmallInteger(), nullable=False),
        sa.Column("letzte_inventur_am", sa.Date(), nullable=True),
        sa.Column("naechste_inventur_am", sa.Date(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_inventurzyklen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["lager_id"], ["anlagen.id"], name="fk_inventurzyklen_lager_id_anlagen"),
        sa.UniqueConstraint("lager_id", name="uq_inventurzyklen_lager"),
        sa.CheckConstraint("intervall_tage > 0", name="ck_inventurzyklen_intervall_positiv"),
    )
    op.execute(
        "CREATE TRIGGER trg_inventurzyklen_updated_at BEFORE UPDATE ON inventurzyklen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_inventurzyklen_mandant_id", "inventurzyklen", ["mandant_id"])
    # Der taegliche Scheduler-Lauf fragt "welche aktiven Zyklen sind heute
    # oder frueher faellig" -- ein partieller Index deckt genau das ab,
    # analog zu idx_pruefzyklen_faellig.
    op.execute(
        "CREATE INDEX idx_inventurzyklen_faellig ON inventurzyklen (mandant_id, naechste_inventur_am) "
        "WHERE aktiv"
    )

    op.execute("ALTER TABLE inventurzyklen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inventurzyklen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("inventurzyklen"))


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON inventurzyklen")
    op.drop_table("inventurzyklen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON fahrzeug_zuweisungen")
    op.drop_table("fahrzeug_zuweisungen")
