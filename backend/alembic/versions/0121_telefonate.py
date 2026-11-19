"""Telefonate (Konzept telefonate, Etappe A-C).

Eigene Tabelle statt Kommentar mit Zusatzfeldern: nur so gibt es Telefonate ohne
Vorgang (nur am Kunden), den Kontaktverlauf am Kunden und die Liste offener
Rueckrufe. Am Vorgang entsteht zusaetzlich ein Verlauf-Event (event_type
'telefonat'), damit der Verlauf weiter aus einer Quelle kommt.

- telefonate: RLS-Policy + FORCE + updated_at-Trigger nach Repo-Konvention.
- vorgang_events: Check-Constraint um 'telefonat' erweitert.

Downgrade: Events vom Typ 'telefonat' werden geloescht (wie in 0052/0118), bevor
der alte Constraint zurueckkommt.

Revision ID: 0121
Revises: 0120
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.migrations_helfer import rls_fuer_backfill_aufheben

revision: str = "0121"
down_revision: Union[str, None] = "0120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALTE_EVENT_TYPEN = (
    "kommentar", "status_change", "foto", "dokument", "mangel", "angebot", "material",
    "zeit_start", "zeit_stop", "termin", "rechnung_status", "system", "unterschrift",
    "eingangsrechnung_status", "formular", "leistung",
    "zuordnung_geaendert", "eigenstaendig_gesetzt", "eigenstaendig_aufgehoben",
)
_NEUE_EVENT_TYPEN = _ALTE_EVENT_TYPEN + ("telefonat",)


def _event_constraint_setzen(typen: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE vorgang_events DROP CONSTRAINT ck_vorgang_events_event_type_valid")
    op.execute(
        "ALTER TABLE vorgang_events ADD CONSTRAINT ck_vorgang_events_event_type_valid "
        f"CHECK (event_type IN {typen})"
    )


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        WITH CHECK (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        """
    )


def upgrade() -> None:
    op.create_table(
        "telefonate",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Kein FK: Id aus der JSONB-Liste kunden.ansprechpartner; Name/Nummer stehen als Kopie daneben.
        sa.Column("ansprechpartner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("partner_name", sa.Text(), nullable=False),
        sa.Column("partner_nummer", sa.Text(), nullable=True),
        sa.Column("richtung", sa.Text(), nullable=False),
        sa.Column("ergebnis", sa.Text(), nullable=False),
        sa.Column("erstellt_via", sa.Text(), nullable=False, server_default="app"),
        sa.Column("beginn", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("dauer_sekunden", sa.Integer(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("rueckruf_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rueckruf_erledigt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rueckruf_benachrichtigt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("zeiterfassung_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erfasst_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("geloescht_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_telefonate_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["kunde_id"], ["kunden.id"], name="fk_telefonate_kunde_id_kunden", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_telefonate_vorgang_id_vorgaenge", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["zeiterfassung_id"], ["zeiterfassung.id"],
            name="fk_telefonate_zeiterfassung_id_zeiterfassung", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["erfasst_von"], ["users.id"], name="fk_telefonate_erfasst_von_users"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_telefonate_geloescht_von_users"),
        sa.CheckConstraint("richtung IN ('ausgehend', 'eingehend')", name="ck_telefonate_richtung_valid"),
        sa.CheckConstraint(
            "ergebnis IN ('erreicht', 'nicht_erreicht', 'mailbox')", name="ck_telefonate_ergebnis_valid"
        ),
        sa.CheckConstraint("erstellt_via IN ('app', 'claude')", name="ck_telefonate_erstellt_via_valid"),
        sa.CheckConstraint(
            "kunde_id IS NOT NULL OR vorgang_id IS NOT NULL", name="ck_telefonate_kunde_oder_vorgang"
        ),
        sa.CheckConstraint(
            "dauer_sekunden IS NULL OR dauer_sekunden >= 0", name="ck_telefonate_dauer_nicht_negativ"
        ),
        sa.UniqueConstraint("client_uuid", name="uq_telefonate_client_uuid"),
    )
    op.create_index("ix_telefonate_mandant_id", "telefonate", ["mandant_id"])
    op.create_index("ix_telefonate_mandant_kunde_beginn", "telefonate", ["mandant_id", "kunde_id", "beginn"])
    op.create_index("ix_telefonate_mandant_vorgang", "telefonate", ["mandant_id", "vorgang_id"])
    op.create_index(
        "ix_telefonate_offene_rueckrufe",
        "telefonate",
        ["rueckruf_am"],
        postgresql_where=sa.text("rueckruf_erledigt_am IS NULL AND geloescht_am IS NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_telefonate_updated_at BEFORE UPDATE ON telefonate "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("telefonate")

    _event_constraint_setzen(_NEUE_EVENT_TYPEN)


def downgrade() -> None:
    # Policy-Prinzip der 0052/0118: Events des neuen Typs gehen mit, sonst scheitert der alte Constraint.
    # vorgang_events ist per FORCE RLS geschuetzt -> kurz aufheben (siehe app/db/migrations_helfer.py).
    with rls_fuer_backfill_aufheben("vorgang_events"):
        op.execute("DELETE FROM vorgang_events WHERE event_type = 'telefonat'")
    _event_constraint_setzen(_ALTE_EVENT_TYPEN)

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON telefonate")
    op.drop_table("telefonate")
