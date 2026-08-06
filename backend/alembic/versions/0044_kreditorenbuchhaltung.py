"""Kreditorenbuchhaltung: Skonto-Felder an Eingangsrechnung + Teilzahlungs-
ledger (eingangsrechnung_zahlungen). Positionen sind statische Belegzeilen
ohne Zeitstempel, eine Zahlung dagegen ist ein Ereignis -- daher analog zu
MaterialBewegung ein rein additives Buchungsprotokoll mit eigenem
created_at statt einer bloss vom Nutzer aktualisierbaren Positionszeile.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: Union[str, None] = "0043"
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
    op.add_column("eingangsrechnungen", sa.Column("skonto_prozent", sa.Numeric(5, 2), nullable=True))
    op.add_column("eingangsrechnungen", sa.Column("skonto_tage", sa.SmallInteger(), nullable=True))

    op.create_table(
        "eingangsrechnung_zahlungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eingangsrechnung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("betrag", sa.Numeric(10, 2), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_eingangsrechnung_zahlungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["eingangsrechnung_id"], ["eingangsrechnungen.id"],
            name="fk_eingangsrechnung_zahlungen_eingangsrechnung_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["erstellt_von"], ["users.id"], name="fk_eingangsrechnung_zahlungen_erstellt_von_users"
        ),
        sa.CheckConstraint("betrag > 0", name="ck_eingangsrechnung_zahlungen_betrag_positiv"),
    )
    op.create_index(
        "ix_eingangsrechnung_zahlungen_eingangsrechnung_id",
        "eingangsrechnung_zahlungen",
        ["eingangsrechnung_id"],
    )
    op.execute("ALTER TABLE eingangsrechnung_zahlungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eingangsrechnung_zahlungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("eingangsrechnung_zahlungen"))


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON eingangsrechnung_zahlungen")
    op.drop_table("eingangsrechnung_zahlungen")
    op.drop_column("eingangsrechnungen", "skonto_tage")
    op.drop_column("eingangsrechnungen", "skonto_prozent")
