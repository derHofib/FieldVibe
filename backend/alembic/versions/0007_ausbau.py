"""Phase 7: kundenportal_zugaenge, highlights, material, material_verwendungen (Ausbau)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
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
    # --- kundenportal_zugaenge -------------------------------------------
    op.create_table(
        "kundenportal_zugaenge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_kundenportal_zugaenge_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_kundenportal_zugaenge_kunde_id_kunden"),
        sa.UniqueConstraint("email", name="uq_kundenportal_zugaenge_email"),
    )
    op.execute(
        "CREATE TRIGGER trg_kundenportal_zugaenge_updated_at BEFORE UPDATE ON kundenportal_zugaenge "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_kundenportal_zugaenge_mandant_id", "kundenportal_zugaenge", ["mandant_id"])
    op.create_index("ix_kundenportal_zugaenge_kunde_id", "kundenportal_zugaenge", ["kunde_id"])
    op.execute("ALTER TABLE kundenportal_zugaenge ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE kundenportal_zugaenge FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("kundenportal_zugaenge"))

    # --- highlights --------------------------------------------------------
    op.create_table(
        "highlights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_event_id", sa.BigInteger(), nullable=False),
        sa.Column("titel", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_highlights_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["vorgang_event_id"], ["vorgang_events.id"], name="fk_highlights_vorgang_event_id_vorgang_events"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_highlights_erstellt_von_users"),
        sa.UniqueConstraint("vorgang_event_id", name="uq_highlights_vorgang_event_id"),
    )
    op.create_index("ix_highlights_mandant_id", "highlights", ["mandant_id"])
    op.execute("ALTER TABLE highlights ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE highlights FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("highlights"))

    # --- material / material_verwendungen ---------------------------------
    op.create_table(
        "material",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("bestand", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("mindestbestand", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_material_mandant_id_mandanten"),
        sa.CheckConstraint("bestand >= 0", name="ck_material_bestand_nicht_negativ"),
    )
    op.execute(
        "CREATE TRIGGER trg_material_updated_at BEFORE UPDATE ON material "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_material_mandant_id", "material", ["mandant_id"])
    op.execute(
        "CREATE INDEX idx_material_unterbestand ON material (mandant_id) WHERE bestand <= mindestbestand"
    )
    op.execute("ALTER TABLE material ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE material FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("material"))

    op.create_table(
        "material_verwendungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False),
        sa.Column("verwendet_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_material_verwendungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["material.id"], name="fk_material_verwendungen_material_id_material"
        ),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_material_verwendungen_vorgang_id_vorgaenge"
        ),
        sa.ForeignKeyConstraint(
            ["verwendet_von"], ["users.id"], name="fk_material_verwendungen_verwendet_von_users"
        ),
        sa.CheckConstraint("menge > 0", name="ck_material_verwendungen_menge_positiv"),
    )
    op.create_index("ix_material_verwendungen_mandant_id", "material_verwendungen", ["mandant_id"])
    op.create_index("ix_material_verwendungen_vorgang_id", "material_verwendungen", ["vorgang_id"])
    op.execute("ALTER TABLE material_verwendungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE material_verwendungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("material_verwendungen"))


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON material_verwendungen")
    op.drop_table("material_verwendungen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON material")
    op.drop_table("material")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON highlights")
    op.drop_table("highlights")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON kundenportal_zugaenge")
    op.drop_table("kundenportal_zugaenge")
