"""Phase 4: zeiterfassung (Feld-Tauglichkeit)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zeiterfassung",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("techniker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ende_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("taetigkeit", sa.Text(), nullable=True),
        sa.Column("abrechenbar", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("freigegeben", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_zeiterfassung_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_zeiterfassung_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["techniker_id"], ["users.id"], name="fk_zeiterfassung_techniker_id_users"),
        sa.CheckConstraint("ende_at IS NULL OR ende_at > start_at", name="ck_zeiterfassung_ende_after_start"),
    )
    op.execute(
        "CREATE TRIGGER trg_zeiterfassung_updated_at BEFORE UPDATE ON zeiterfassung "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_zeiterfassung_mandant_id", "zeiterfassung", ["mandant_id"])
    op.create_index("ix_zeiterfassung_vorgang_id", "zeiterfassung", ["vorgang_id"])
    # Ein Techniker darf pro Zeitpunkt nur einen laufenden Timer haben
    # (Abschnitt 4.7) -- als partieller Unique-Index erzwungen, nicht nur
    # als Anwendungslogik geprueft.
    op.execute(
        "CREATE UNIQUE INDEX ux_zeiterfassung_ein_laufender_timer "
        "ON zeiterfassung (techniker_id) WHERE ende_at IS NULL"
    )

    op.execute("ALTER TABLE zeiterfassung ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE zeiterfassung FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON zeiterfassung
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
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON zeiterfassung")
    op.drop_table("zeiterfassung")
