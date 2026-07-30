"""Dauerauftraege: mehrere Anlagen pro Dauerauftrag buendeln
(dauerauftrag_ziele) statt einer einzelnen anlage_id -- jedes Ziel
(Kunde direkt oder eine bestimmte Anlage) hat sein eigenes
naechste_faelligkeit_am/offener_vorgang_id, damit sich die Zyklen
unabhaengig voneinander weiterdrehen.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dauerauftrag_ziele",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dauerauftrag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("naechste_faelligkeit_am", sa.Date(), nullable=False),
        sa.Column("offener_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_dauerauftrag_ziele_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["dauerauftrag_id"], ["dauerauftraege.id"],
            name="fk_dauerauftrag_ziele_dauerauftrag_id_dauerauftraege", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_dauerauftrag_ziele_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(
            ["offener_vorgang_id"], ["vorgaenge.id"], name="fk_dauerauftrag_ziele_offener_vorgang_id_vorgaenge"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_dauerauftrag_ziele_updated_at BEFORE UPDATE ON dauerauftrag_ziele "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_dauerauftrag_ziele_mandant_id", "dauerauftrag_ziele", ["mandant_id"])
    op.create_index("ix_dauerauftrag_ziele_dauerauftrag_id", "dauerauftrag_ziele", ["dauerauftrag_id"])
    # Ein Dauerauftrag darf eine bestimmte Anlage nur einmal als Ziel haben;
    # NULL (kein spezifisches Asset, gilt fuer den Kunden direkt) ebenfalls
    # hoechstens einmal -- zwei partielle Unique-Indizes statt eines
    # einzelnen Constraints, weil Postgres NULLs sonst nicht als gleich
    # behandelt.
    op.execute(
        "CREATE UNIQUE INDEX uq_dauerauftrag_ziele_dauerauftrag_anlage "
        "ON dauerauftrag_ziele (dauerauftrag_id, anlage_id) WHERE anlage_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_dauerauftrag_ziele_dauerauftrag_ohne_anlage "
        "ON dauerauftrag_ziele (dauerauftrag_id) WHERE anlage_id IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_dauerauftrag_ziele_faellig ON dauerauftrag_ziele "
        "(mandant_id, naechste_faelligkeit_am) WHERE offener_vorgang_id IS NULL"
    )

    op.execute("ALTER TABLE dauerauftrag_ziele ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dauerauftrag_ziele FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON dauerauftrag_ziele
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

    # Bestehende Dauerauftraege 1:1 in ein einzelnes Ziel ueberfuehren --
    # ihr bisheriges Verhalten (eine Anlage oder gar keine) bleibt dadurch
    # unveraendert erhalten, nur eben jetzt als Sonderfall "ein Ziel" der
    # neuen, allgemeineren Struktur.
    op.execute(
        """
        INSERT INTO dauerauftrag_ziele
            (id, mandant_id, dauerauftrag_id, anlage_id, naechste_faelligkeit_am, offener_vorgang_id, created_at, updated_at)
        SELECT gen_random_uuid(), mandant_id, id, anlage_id, naechste_faelligkeit_am, offener_vorgang_id, created_at, updated_at
        FROM dauerauftraege
        """
    )

    op.drop_constraint("fk_dauerauftraege_offener_vorgang_id_vorgaenge", "dauerauftraege", type_="foreignkey")
    op.drop_constraint("fk_dauerauftraege_anlage_id_anlagen", "dauerauftraege", type_="foreignkey")
    op.drop_index("idx_dauerauftraege_faellig", table_name="dauerauftraege")
    op.drop_column("dauerauftraege", "offener_vorgang_id")
    op.drop_column("dauerauftraege", "anlage_id")
    op.drop_column("dauerauftraege", "naechste_faelligkeit_am")


def downgrade() -> None:
    op.add_column("dauerauftraege", sa.Column("naechste_faelligkeit_am", sa.Date(), nullable=True))
    op.add_column("dauerauftraege", sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("dauerauftraege", sa.Column("offener_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True))

    # Nur das erste Ziel je Dauerauftrag passt zurueck in die alten
    # skalaren Spalten -- Buendel mit mehreren Anlagen verlieren beim
    # Downgrade zwangslaeufig alle bis auf ein Ziel.
    op.execute(
        """
        UPDATE dauerauftraege d
        SET anlage_id = z.anlage_id,
            naechste_faelligkeit_am = z.naechste_faelligkeit_am,
            offener_vorgang_id = z.offener_vorgang_id
        FROM (
            SELECT DISTINCT ON (dauerauftrag_id) dauerauftrag_id, anlage_id, naechste_faelligkeit_am, offener_vorgang_id
            FROM dauerauftrag_ziele
            ORDER BY dauerauftrag_id, created_at
        ) z
        WHERE d.id = z.dauerauftrag_id
        """
    )
    op.alter_column("dauerauftraege", "naechste_faelligkeit_am", nullable=False)

    op.create_foreign_key(
        "fk_dauerauftraege_anlage_id_anlagen", "dauerauftraege", "anlagen", ["anlage_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_dauerauftraege_offener_vorgang_id_vorgaenge", "dauerauftraege", "vorgaenge",
        ["offener_vorgang_id"], ["id"],
    )
    op.execute(
        "CREATE INDEX idx_dauerauftraege_faellig ON dauerauftraege (mandant_id, naechste_faelligkeit_am) "
        "WHERE aktiv AND offener_vorgang_id IS NULL"
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON dauerauftrag_ziele")
    op.drop_table("dauerauftrag_ziele")
