"""Material-Bestellwesen: Lieferanten-Stammdaten, Materialbedarfe an
Vorgaengen (fuer Beschaffung ODER als Kalkulationsgrundlage fuer ein
Angebot bei Planungs-/Beratungs-Vorgaengen) und Bestellungen, die
ausgewaehlte Bedarfe zu einer exportierbaren Sammelbestellung an einen
Lieferanten buendeln.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
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
    # --- lieferanten -----------------------------------------------------
    op.create_table(
        "lieferanten",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("telefon", sa.Text(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_lieferanten_mandant_id_mandanten"),
    )
    op.execute(
        "CREATE TRIGGER trg_lieferanten_updated_at BEFORE UPDATE ON lieferanten "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_lieferanten_mandant_id", "lieferanten", ["mandant_id"])
    _enable_rls("lieferanten")

    # --- material: optionaler Standard-Lieferant --------------------------
    op.add_column("material", sa.Column("lieferant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_material_lieferant_id_lieferanten", "material", "lieferanten", ["lieferant_id"], ["id"]
    )

    # --- bestellungen ------------------------------------------------------
    op.create_table(
        "bestellungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lieferant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bestellnummer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="entwurf"),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_bestellungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["lieferant_id"], ["lieferanten.id"], name="fk_bestellungen_lieferant_id_lieferanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_bestellungen_erstellt_von_users"),
        sa.UniqueConstraint(
            "mandant_id", "bestellnummer", name=op.f("uq_bestellungen_mandant_bestellnummer")
        ),
        sa.CheckConstraint(
            "status IN ('entwurf', 'bestellt', 'eingegangen')", name=op.f("ck_bestellungen_status_valid")
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_bestellungen_updated_at BEFORE UPDATE ON bestellungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_bestellungen_mandant_id", "bestellungen", ["mandant_id"])
    _enable_rls("bestellungen")

    # --- material_bedarfe ---------------------------------------------------
    op.create_table(
        "material_bedarfe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("zweck", sa.Text(), nullable=False, server_default="bestellung"),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("bestellung_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("angebot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_material_bedarfe_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"], name="fk_material_bedarfe_material_id_material"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_material_bedarfe_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(
            ["bestellung_id"], ["bestellungen.id"], name="fk_material_bedarfe_bestellung_id_bestellungen"
        ),
        sa.ForeignKeyConstraint(["angebot_id"], ["angebote.id"], name="fk_material_bedarfe_angebot_id_angebote"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_material_bedarfe_erstellt_von_users"),
        sa.CheckConstraint("menge > 0", name=op.f("ck_material_bedarfe_menge_positiv")),
        sa.CheckConstraint(
            "zweck IN ('bestellung', 'angebot')", name=op.f("ck_material_bedarfe_zweck_valid")
        ),
        sa.CheckConstraint(
            "status IN ('offen', 'bestellt', 'in_angebot', 'erhalten', 'storniert')",
            name=op.f("ck_material_bedarfe_status_valid"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_material_bedarfe_updated_at BEFORE UPDATE ON material_bedarfe "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_material_bedarfe_mandant_id", "material_bedarfe", ["mandant_id"])
    op.create_index("ix_material_bedarfe_vorgang_id", "material_bedarfe", ["vorgang_id"])
    op.create_index("ix_material_bedarfe_status", "material_bedarfe", ["status"])
    _enable_rls("material_bedarfe")

    # --- bestellung_positionen ----------------------------------------------
    op.create_table(
        "bestellung_positionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bestellung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_bestellung_positionen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["bestellung_id"],
            ["bestellungen.id"],
            name="fk_bestellung_positionen_bestellung_id_bestellungen",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["material.id"], name="fk_bestellung_positionen_material_id_material"
        ),
        sa.CheckConstraint("menge > 0", name=op.f("ck_bestellung_positionen_menge_positiv")),
    )
    op.create_index("ix_bestellung_positionen_mandant_id", "bestellung_positionen", ["mandant_id"])
    op.create_index("ix_bestellung_positionen_bestellung_id", "bestellung_positionen", ["bestellung_id"])
    _enable_rls("bestellung_positionen")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON bestellung_positionen")
    op.drop_table("bestellung_positionen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON material_bedarfe")
    op.drop_table("material_bedarfe")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON bestellungen")
    op.drop_table("bestellungen")

    op.drop_constraint("fk_material_lieferant_id_lieferanten", "material", type_="foreignkey")
    op.drop_column("material", "lieferant_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON lieferanten")
    op.drop_table("lieferanten")
