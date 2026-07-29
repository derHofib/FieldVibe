"""Phase 5: termine, pruefzyklen, pruefmittel (Steuerung)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TERMIN_STATUS = ("geplant", "bestaetigt", "abgeschlossen", "abgesagt")
PRUEFMITTEL_STATUS = ("aktiv", "defekt", "ausser_betrieb")


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
    # --- termine ------------------------------------------------------
    op.create_table(
        "termine",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("techniker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("start_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ende_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="geplant"),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_termine_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_termine_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["techniker_id"], ["users.id"], name="fk_termine_techniker_id_users"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_termine_erstellt_von_users"),
        sa.CheckConstraint("ende_at > start_at", name="ck_termine_ende_after_start"),
        sa.CheckConstraint(f"status IN {TERMIN_STATUS}", name="ck_termine_status_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_termine_updated_at BEFORE UPDATE ON termine "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_termine_mandant_id", "termine", ["mandant_id"])
    op.create_index("ix_termine_vorgang_id", "termine", ["vorgang_id"])
    # Dispo-Board und Konflikt-/Ueberschneidungspruefung fragen immer nach
    # "Termine eines Technikers in einem Zeitraum" -- ein zusammengesetzter
    # Index darauf statt getrennter Indizes auf techniker_id/start_at.
    op.create_index("idx_termine_techniker", "termine", ["techniker_id", "start_at"])

    op.execute("ALTER TABLE termine ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE termine FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("termine"))

    # --- pruefzyklen ----------------------------------------------------
    op.create_table(
        "pruefzyklen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("intervall_monate", sa.SmallInteger(), nullable=False),
        sa.Column("letzte_pruefung_am", sa.Date(), nullable=True),
        sa.Column("naechste_pruefung_am", sa.Date(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("offener_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_pruefzyklen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_pruefzyklen_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(
            ["offener_vorgang_id"], ["vorgaenge.id"], name="fk_pruefzyklen_offener_vorgang_id_vorgaenge"
        ),
        sa.CheckConstraint("intervall_monate > 0", name="ck_pruefzyklen_intervall_positiv"),
    )
    op.execute(
        "CREATE TRIGGER trg_pruefzyklen_updated_at BEFORE UPDATE ON pruefzyklen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_pruefzyklen_mandant_id", "pruefzyklen", ["mandant_id"])
    op.create_index("ix_pruefzyklen_anlage_id", "pruefzyklen", ["anlage_id"])
    # Der taegliche Scheduler fragt "welche Zyklen sind heute oder frueher
    # faellig", eingeschraenkt auf aktive Zyklen -- ein partieller
    # zusammengesetzter Index deckt genau diese Abfrage ab.
    op.execute(
        "CREATE INDEX idx_pruefzyklen_faellig ON pruefzyklen (mandant_id, naechste_pruefung_am) "
        "WHERE aktiv"
    )

    op.execute("ALTER TABLE pruefzyklen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pruefzyklen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("pruefzyklen"))

    # --- pruefmittel ------------------------------------------------------
    op.create_table(
        "pruefmittel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("seriennummer", sa.Text(), nullable=True),
        sa.Column("zugewiesen_an", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kalibrierintervall_monate", sa.SmallInteger(), nullable=False),
        sa.Column("letzte_kalibrierung_am", sa.Date(), nullable=True),
        sa.Column("naechste_kalibrierung_am", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="aktiv"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_pruefmittel_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["zugewiesen_an"], ["users.id"], name="fk_pruefmittel_zugewiesen_an_users"),
        sa.CheckConstraint("kalibrierintervall_monate > 0", name="ck_pruefmittel_intervall_positiv"),
        sa.CheckConstraint(f"status IN {PRUEFMITTEL_STATUS}", name="ck_pruefmittel_status_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_pruefmittel_updated_at BEFORE UPDATE ON pruefmittel "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_pruefmittel_mandant_id", "pruefmittel", ["mandant_id"])
    op.execute(
        "CREATE INDEX idx_pruefmittel_faellig ON pruefmittel (mandant_id, naechste_kalibrierung_am) "
        "WHERE status = 'aktiv'"
    )

    op.execute("ALTER TABLE pruefmittel ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pruefmittel FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("pruefmittel"))


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON pruefmittel")
    op.drop_table("pruefmittel")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON pruefzyklen")
    op.drop_table("pruefzyklen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON termine")
    op.drop_table("termine")
