"""Rechnungseingang Grundmodell: eingangsrechnungen + eingangsrechnung_positionen.

Erfasst Belege, die der Mandant von Lieferanten/Dienstleistern erhaelt
(Wareneinkauf, Miete, Versicherung, ...) -- Gegenstueck zu den bereits
bestehenden ausgehenden Rechnungen. Anders als bei Rechnung braucht es
hier keine eigene Nummernvergabe: rechnungsnummer_lieferant ist die vom
Aussteller vergebene Nummer, reine Freitexteingabe. Ebenso keine eigene
Storno-Beleg-Logik -- der GoBD-Unveraenderbarkeitsgrundsatz betrifft hier
den unveraendert archivierten Beleg-Upload (beleg_object_key), nicht die
Metadaten, die wir selbst erfassen.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EINGANGSRECHNUNG_STATUS = ("offen", "bezahlt", "storniert")
EINGANGSRECHNUNG_KATEGORIEN = (
    "wareneinkauf", "betriebskosten", "miete", "personal", "fahrzeug", "versicherung", "sonstiges",
)

_OLD_EVENT_TYPEN = (
    "kommentar", "status_change", "foto", "dokument", "mangel",
    "angebot", "material", "zeit_start", "zeit_stop", "termin",
    "rechnung_status", "system", "unterschrift",
)
_NEW_EVENT_TYPEN = _OLD_EVENT_TYPEN + ("eingangsrechnung_status",)


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
    op.create_table(
        "eingangsrechnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lieferant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lieferant_name", sa.Text(), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rechnungsnummer_lieferant", sa.Text(), nullable=False),
        sa.Column("rechnungsdatum", sa.Date(), nullable=False),
        sa.Column("eingegangen_am", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("faellig_am", sa.Date(), nullable=True),
        sa.Column("betrag_netto", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("mwst_satz", sa.Numeric(5, 2), nullable=False, server_default="19.00"),
        sa.Column("kategorie", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("bezahlt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("beleg_object_key", sa.Text(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geloescht_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_eingangsrechnungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["lieferant_id"], ["lieferanten.id"], name="fk_eingangsrechnungen_lieferant_id_lieferanten"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_eingangsrechnungen_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_eingangsrechnungen_erstellt_von_users"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_eingangsrechnungen_geloescht_von_users"),
        sa.CheckConstraint(f"status IN {EINGANGSRECHNUNG_STATUS}", name="ck_eingangsrechnungen_status_valid"),
        sa.CheckConstraint(
            f"kategorie IS NULL OR kategorie IN {EINGANGSRECHNUNG_KATEGORIEN}",
            name="ck_eingangsrechnungen_kategorie_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_eingangsrechnungen_updated_at BEFORE UPDATE ON eingangsrechnungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_eingangsrechnungen_mandant_id", "eingangsrechnungen", ["mandant_id"])
    op.create_index("ix_eingangsrechnungen_lieferant_id", "eingangsrechnungen", ["lieferant_id"])
    op.create_index("ix_eingangsrechnungen_vorgang_id", "eingangsrechnungen", ["vorgang_id"])
    op.execute("ALTER TABLE eingangsrechnungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eingangsrechnungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("eingangsrechnungen"))

    op.create_table(
        "eingangsrechnung_positionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eingangsrechnung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_eingangsrechnung_positionen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["eingangsrechnung_id"], ["eingangsrechnungen.id"],
            name="fk_eingangsrechnung_positionen_eingangsrechnung_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_eingangsrechnung_positionen_eingangsrechnung_id",
        "eingangsrechnung_positionen",
        ["eingangsrechnung_id"],
    )
    op.execute("ALTER TABLE eingangsrechnung_positionen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eingangsrechnung_positionen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("eingangsrechnung_positionen"))

    op.drop_constraint(op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", type_="check")
    op.create_check_constraint(
        op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", f"event_type IN {_NEW_EVENT_TYPEN}"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", type_="check")
    op.create_check_constraint(
        op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", f"event_type IN {_OLD_EVENT_TYPEN}"
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON eingangsrechnung_positionen")
    op.drop_table("eingangsrechnung_positionen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON eingangsrechnungen")
    op.drop_table("eingangsrechnungen")
