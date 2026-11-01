"""SLA-Richtlinien (docs/konzepte/SLA.md, Phase 2): sla_richtlinien,
sla_eskalationsstufen und vertraege.sla_richtlinie_id.

Die Vorgangs-Snapshotfelder und die Eskalationsprotokolle folgen mit den
Phasen 3 und 4. Downgrade verwirft Richtlinien und Stufen; die Spalte am Vertrag
wird entfernt.

Revision ID: 0116
Revises: 0115
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0116"
down_revision: Union[str, None] = "0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KALENDER = ("rund_um_die_uhr", "geschaeftszeiten")
_FRIST_ART = ("reaktion", "loesung")
_AKTION = ("benachrichtigen", "mail")
_EMPFAENGER = ("zugewiesener", "dispo", "vorgesetzter", "admin")


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
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.create_table(
        "sla_richtlinien",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ist_standard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kalender", sa.Text(), nullable=False, server_default="rund_um_die_uhr"),
        sa.Column("geschaeftszeiten", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feiertage_ausnehmen", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ziele", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        # Leistungstyp -> Prioritaet: je Richtlinie (= je Vertrag) eigene Regeln.
        sa.Column("prioritaet_regeln", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_sla_richtlinien_mandant_id_mandanten"),
        sa.CheckConstraint(f"kalender IN {_KALENDER}", name=op.f("ck_sla_richtlinien_kalender_valid")),
        sa.UniqueConstraint("mandant_id", "name", name="uq_sla_richtlinien_mandant_name"),
    )
    op.create_index(
        "uq_sla_richtlinien_standard", "sla_richtlinien", ["mandant_id"],
        unique=True, postgresql_where=sa.text("ist_standard"),
    )
    op.execute(
        "CREATE TRIGGER trg_sla_richtlinien_updated_at BEFORE UPDATE ON sla_richtlinien "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("sla_richtlinien")

    op.create_table(
        "sla_eskalationsstufen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("richtlinie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frist_art", sa.Text(), nullable=False),
        sa.Column("schwelle_prozent", sa.SmallInteger(), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("empfaenger", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_sla_stufen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["richtlinie_id"], ["sla_richtlinien.id"], name="fk_sla_stufen_richtlinie_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint(f"frist_art IN {_FRIST_ART}", name=op.f("ck_sla_stufen_frist_art_valid")),
        sa.CheckConstraint(f"aktion IN {_AKTION}", name=op.f("ck_sla_stufen_aktion_valid")),
        sa.CheckConstraint(f"empfaenger IN {_EMPFAENGER}", name=op.f("ck_sla_stufen_empfaenger_valid")),
        sa.CheckConstraint("schwelle_prozent BETWEEN 1 AND 500", name=op.f("ck_sla_stufen_schwelle_bereich")),
    )
    op.create_index("ix_sla_stufen_richtlinie_id", "sla_eskalationsstufen", ["richtlinie_id"])
    op.execute(
        "CREATE TRIGGER trg_sla_stufen_updated_at BEFORE UPDATE ON sla_eskalationsstufen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("sla_eskalationsstufen")

    op.add_column(
        "vertraege",
        sa.Column(
            "sla_richtlinie_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sla_richtlinien.id", name="fk_vertraege_sla_richtlinie_id"), nullable=True,
        ),
    )
    op.create_index("ix_vertraege_sla_richtlinie_id", "vertraege", ["sla_richtlinie_id"])


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_index("ix_vertraege_sla_richtlinie_id", table_name="vertraege")
    op.drop_column("vertraege", "sla_richtlinie_id")
    op.drop_table("sla_eskalationsstufen")
    op.drop_table("sla_richtlinien")
