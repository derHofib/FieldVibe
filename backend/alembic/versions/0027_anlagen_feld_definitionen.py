"""Mandantenkonfigurierbare Zusatzfeld-Definitionen je Anlagentyp
(z.B. "Kennzeichen" fuer Fahrzeuge, "Leistung kW" fuer Ladestationen) --
die eigentlichen Werte landen im bestehenden Anlage.stammdaten JSONB.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
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
        "anlagen_feld_definitionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlagentyp", sa.Text(), nullable=False),
        sa.Column("feld_name", sa.Text(), nullable=False),
        sa.Column("feld_typ", sa.Text(), nullable=False, server_default="text"),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_anlagen_feld_definitionen_mandant_id_mandanten"
        ),
        sa.UniqueConstraint(
            "mandant_id", "anlagentyp", "feld_name", name=op.f("uq_anlagen_feld_def_mandant_typ_name")
        ),
        sa.CheckConstraint(
            "feld_typ IN ('text', 'zahl', 'datum')", name=op.f("ck_anlagen_feld_def_typ_valid")
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_anlagen_feld_definitionen_updated_at BEFORE UPDATE ON anlagen_feld_definitionen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index(
        "ix_anlagen_feld_definitionen_mandant_id", "anlagen_feld_definitionen", ["mandant_id"]
    )
    op.create_index(
        "ix_anlagen_feld_definitionen_anlagentyp", "anlagen_feld_definitionen", ["anlagentyp"]
    )
    _enable_rls("anlagen_feld_definitionen")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON anlagen_feld_definitionen")
    op.drop_table("anlagen_feld_definitionen")
