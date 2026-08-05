"""Dauerauftraege: wiederkehrende Auftraege (Kunde + optional Anlage,
Intervall in Tagen, dupliziert sich nach Abschluss automatisch neu)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ABRECHNUNGSARTEN_VORGANG = ("pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung")
LEISTUNGSTYPEN = ("installation", "pruefung", "wartung", "stoerung", "beratung", "planung")


def upgrade() -> None:
    op.create_table(
        "dauerauftraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("abrechnungsart", sa.Text(), nullable=False),
        sa.Column("leistungstyp", sa.Text(), nullable=False),
        sa.Column("intervall_tage", sa.SmallInteger(), nullable=False),
        sa.Column("naechste_faelligkeit_am", sa.Date(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("offener_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_dauerauftraege_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_dauerauftraege_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_dauerauftraege_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(
            ["offener_vorgang_id"], ["vorgaenge.id"], name="fk_dauerauftraege_offener_vorgang_id_vorgaenge"
        ),
        sa.CheckConstraint("intervall_tage > 0", name="ck_dauerauftraege_intervall_positiv"),
        sa.CheckConstraint(
            f"abrechnungsart IN {ABRECHNUNGSARTEN_VORGANG}",
            name="ck_dauerauftraege_abrechnungsart_valid",
        ),
        sa.CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}", name="ck_dauerauftraege_leistungstyp_valid"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_dauerauftraege_updated_at BEFORE UPDATE ON dauerauftraege "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_dauerauftraege_mandant_id", "dauerauftraege", ["mandant_id"])
    op.create_index("ix_dauerauftraege_kunde_id", "dauerauftraege", ["kunde_id"])
    # Der stuendliche Worker-Tick fragt "welche Dauerauftraege sind heute
    # oder frueher faellig", eingeschraenkt auf aktive und noch nicht
    # offene (kein bereits erzeugter, noch nicht abgeschlossener Vorgang) --
    # ein partieller zusammengesetzter Index deckt genau diese Abfrage ab.
    op.execute(
        "CREATE INDEX idx_dauerauftraege_faellig ON dauerauftraege (mandant_id, naechste_faelligkeit_am) "
        "WHERE aktiv AND offener_vorgang_id IS NULL"
    )

    op.execute("ALTER TABLE dauerauftraege ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dauerauftraege FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON dauerauftraege
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

    op.add_column(
        "vorgaenge", sa.Column("dauerauftrag_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_vorgaenge_dauerauftrag_id_dauerauftraege",
        "vorgaenge",
        "dauerauftraege",
        ["dauerauftrag_id"],
        ["id"],
    )
    op.create_index("ix_vorgaenge_dauerauftrag_id", "vorgaenge", ["dauerauftrag_id"])


def downgrade() -> None:
    op.drop_index("ix_vorgaenge_dauerauftrag_id", table_name="vorgaenge")
    op.drop_constraint("fk_vorgaenge_dauerauftrag_id_dauerauftraege", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "dauerauftrag_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON dauerauftraege")
    op.drop_table("dauerauftraege")
