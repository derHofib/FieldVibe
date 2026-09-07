"""Leistungsverzeichnis: eine Position kann mehreren Kunden zugewiesen sein.

Ersetzt die einfache leistungsverzeichnis_positionen.kunde_id-Spalte (eine
Position -> hoechstens ein Kunde) durch eine echte Many-to-many-Tabelle
leistungsverzeichnis_position_kunden (gleiches Muster wie kunde_zuweisungen,
Migration 0011): eine Position kann keinem, einem oder mehreren Kunden
zugewiesen sein -- kein Eintrag heisst weiterhin "gilt fuer alle Kunden".

Damit zeigt die Leistungsverzeichnis-Uebersichtsseite jetzt ALLE Positionen
eines Mandanten (allgemeine und kundenspezifische zusammen) statt nur den
allgemeinen Katalog, siehe app/api/routes/leistungsverzeichnis.py.

Bestehende kunde_id-Werte werden 1:1 in die neue Tabelle uebernommen, die
Spalte selbst entfaellt danach.

Revision ID: 0075
Revises: 0074
Create Date: 2026-09-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0075"
down_revision: Union[str, None] = "0074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leistungsverzeichnis_position_kunden",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lv_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_leistungsverzeichnis_position_kunden_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["lv_position_id"],
            ["leistungsverzeichnis_positionen.id"],
            name="fk_leistungsverzeichnis_position_kunden_lv_position_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["kunde_id"],
            ["kunden.id"],
            name="fk_leistungsverzeichnis_position_kunden_kunde_id_kunden",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "lv_position_id", "kunde_id", name="uq_leistungsverzeichnis_position_kunden_position_kunde"
        ),
    )
    op.create_index(
        "ix_leistungsverzeichnis_position_kunden_mandant_id", "leistungsverzeichnis_position_kunden", ["mandant_id"]
    )
    op.create_index(
        "ix_leistungsverzeichnis_position_kunden_lv_position_id",
        "leistungsverzeichnis_position_kunden",
        ["lv_position_id"],
    )
    op.create_index(
        "ix_leistungsverzeichnis_position_kunden_kunde_id", "leistungsverzeichnis_position_kunden", ["kunde_id"]
    )

    op.execute("ALTER TABLE leistungsverzeichnis_position_kunden ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leistungsverzeichnis_position_kunden FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON leistungsverzeichnis_position_kunden
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

    op.execute(
        """
        INSERT INTO leistungsverzeichnis_position_kunden (id, mandant_id, lv_position_id, kunde_id, created_at)
        SELECT gen_random_uuid(), mandant_id, id, kunde_id, now()
        FROM leistungsverzeichnis_positionen
        WHERE kunde_id IS NOT NULL
        """
    )

    op.drop_constraint(
        "fk_leistungsverzeichnis_positionen_kunde_id_kunden", "leistungsverzeichnis_positionen", type_="foreignkey"
    )
    op.drop_index("ix_leistungsverzeichnis_positionen_kunde_id", table_name="leistungsverzeichnis_positionen")
    op.drop_column("leistungsverzeichnis_positionen", "kunde_id")


def downgrade() -> None:
    op.add_column(
        "leistungsverzeichnis_positionen", sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    # Downgrade dient nur der lokalen Migrationszyklus-Pruefung -- bei einer
    # Position mit mehreren zugewiesenen Kunden geht dabei absichtlich die
    # Mehrfachzuordnung verloren, es bleibt nur die aelteste Zuweisung.
    op.execute(
        """
        UPDATE leistungsverzeichnis_positionen p
        SET kunde_id = sub.kunde_id
        FROM (
            SELECT DISTINCT ON (lv_position_id) lv_position_id, kunde_id
            FROM leistungsverzeichnis_position_kunden
            ORDER BY lv_position_id, created_at
        ) sub
        WHERE p.id = sub.lv_position_id
        """
    )
    op.create_index(
        "ix_leistungsverzeichnis_positionen_kunde_id", "leistungsverzeichnis_positionen", ["kunde_id"]
    )
    op.create_foreign_key(
        "fk_leistungsverzeichnis_positionen_kunde_id_kunden",
        "leistungsverzeichnis_positionen",
        "kunden",
        ["kunde_id"],
        ["id"],
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON leistungsverzeichnis_position_kunden")
    op.drop_table("leistungsverzeichnis_position_kunden")
