"""Nacharbeiten: rechnung_positionen, Mahnwesen-Spalten auf rechnungen

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
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
    # --- rechnung_positionen (Teil-/Sammelrechnungen mit eigenen Zeilen) --
    op.create_table(
        "rechnung_positionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rechnung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_rechnung_positionen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["rechnung_id"], ["rechnungen.id"], name="fk_rechnung_positionen_rechnung_id_rechnungen",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_rechnung_positionen_rechnung_id", "rechnung_positionen", ["rechnung_id"])
    op.execute("ALTER TABLE rechnung_positionen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rechnung_positionen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("rechnung_positionen"))

    # --- Mahnwesen: einfache Stufen-Eskalation ueberfaelliger Rechnungen --
    op.add_column(
        "rechnungen", sa.Column("mahnstufe", sa.SmallInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "rechnungen", sa.Column("letzte_mahnung_am", sa.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("rechnungen", "letzte_mahnung_am")
    op.drop_column("rechnungen", "mahnstufe")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON rechnung_positionen")
    op.drop_table("rechnung_positionen")
