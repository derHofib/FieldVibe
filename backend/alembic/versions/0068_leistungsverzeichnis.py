"""Leistungsverzeichnis (LV): optionaler, kunden-eigener Katalog aus
wiederverwendbaren Positionen (Pauschalen, Stundenverrechnungssaetze).
leistungsverzeichnis_positionen ist der Katalog (Papierkorb-faehig, wie
material), leistungsverzeichnis_verwendungen ist die Buchung einer Position
an einem Vorgang (analog material_verwendungen, aber ohne Bestandsfuehrung).
Ausserdem: zeiterfassung.lv_position_id (koppelt einen Stundenverrechnungs-
satz an einen Zeiterfassungs-Eintrag) und der neue VorgangEvent-Typ
"leistung".

Revision ID: 0068
Revises: 0067
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068"
down_revision: Union[str, None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_EVENT_TYPEN = (
    "kommentar", "status_change", "foto", "dokument", "mangel", "angebot",
    "material", "zeit_start", "zeit_stop", "termin", "rechnung_status",
    "system", "unterschrift", "eingangsrechnung_status", "formular",
)
_NEW_EVENT_TYPEN = _OLD_EVENT_TYPEN + ("leistung",)


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
    # --- leistungsverzeichnis_positionen -----------------------------------
    op.create_table(
        "leistungsverzeichnis_positionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("ist_stundensatz", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("geloescht_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_leistungsverzeichnis_positionen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["kunde_id"], ["kunden.id"], name="fk_leistungsverzeichnis_positionen_kunde_id_kunden"
        ),
        sa.ForeignKeyConstraint(
            ["geloescht_von"], ["users.id"], name="fk_leistungsverzeichnis_positionen_geloescht_von_users"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_leistungsverzeichnis_positionen_updated_at BEFORE UPDATE "
        "ON leistungsverzeichnis_positionen FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index(
        "ix_leistungsverzeichnis_positionen_mandant_id", "leistungsverzeichnis_positionen", ["mandant_id"]
    )
    op.create_index(
        "ix_leistungsverzeichnis_positionen_kunde_id", "leistungsverzeichnis_positionen", ["kunde_id"]
    )
    _enable_rls("leistungsverzeichnis_positionen")

    # --- leistungsverzeichnis_verwendungen ---------------------------------
    op.create_table(
        "leistungsverzeichnis_verwendungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lv_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False),
        sa.Column("verwendet_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_leistungsverzeichnis_verwendungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["lv_position_id"],
            ["leistungsverzeichnis_positionen.id"],
            name="fk_leistungsverzeichnis_verwendungen_lv_position_id",
        ),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_leistungsverzeichnis_verwendungen_vorgang_id_vorgaenge"
        ),
        sa.ForeignKeyConstraint(
            ["verwendet_von"], ["users.id"], name="fk_leistungsverzeichnis_verwendungen_verwendet_von_users"
        ),
        sa.CheckConstraint("menge > 0", name=op.f("ck_leistungsverzeichnis_verwendungen_menge_positiv")),
    )
    op.create_index(
        "ix_leistungsverzeichnis_verwendungen_mandant_id", "leistungsverzeichnis_verwendungen", ["mandant_id"]
    )
    op.create_index(
        "ix_leistungsverzeichnis_verwendungen_vorgang_id", "leistungsverzeichnis_verwendungen", ["vorgang_id"]
    )
    op.create_index(
        "ix_leistungsverzeichnis_verwendungen_lv_position_id",
        "leistungsverzeichnis_verwendungen",
        ["lv_position_id"],
    )
    _enable_rls("leistungsverzeichnis_verwendungen")

    # --- zeiterfassung: optionaler SVS-Bezug -------------------------------
    op.add_column(
        "zeiterfassung", sa.Column("lv_position_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_zeiterfassung_lv_position_id_leistungsverzeichnis_positionen",
        "zeiterfassung",
        "leistungsverzeichnis_positionen",
        ["lv_position_id"],
        ["id"],
    )

    # --- vorgang_events: neuer Typ "leistung" ------------------------------
    op.drop_constraint(op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", type_="check")
    op.create_check_constraint(
        op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", f"event_type IN {_NEW_EVENT_TYPEN}"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", type_="check")
    op.execute("DELETE FROM vorgang_events WHERE event_type = 'leistung'")
    op.create_check_constraint(
        op.f("ck_vorgang_events_event_type_valid"), "vorgang_events", f"event_type IN {_OLD_EVENT_TYPEN}"
    )

    op.drop_constraint(
        "fk_zeiterfassung_lv_position_id_leistungsverzeichnis_positionen", "zeiterfassung", type_="foreignkey"
    )
    op.drop_column("zeiterfassung", "lv_position_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON leistungsverzeichnis_verwendungen")
    op.drop_table("leistungsverzeichnis_verwendungen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON leistungsverzeichnis_positionen")
    op.drop_table("leistungsverzeichnis_positionen")
