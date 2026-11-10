"""Zeitplan: Aenderungsantraege von Technikern + Rechte zeitplan_sehen/
zeitplan_beantragen im Bereich "projekte".

Die beiden Zusatzaktionen erweitern den CHECK auf account_typ_rechte.aktion.
Backfill: jeder Account-Typ mit projekte.sehen oder dem Seed-Namen
"Techniker" bekommt beide Rechte, damit bestehende Mandanten nach dem Update
nichts Sichtbares verlieren bzw. Techniker den Zeitplan sofort sehen.

Revision ID: 0095
Revises: 0094
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AKTIONEN_ALT = "('sehen', 'erstellen', 'bearbeiten', 'loeschen')"
_AKTIONEN_NEU = "('sehen', 'erstellen', 'bearbeiten', 'loeschen', 'zeitplan_sehen', 'zeitplan_beantragen')"


def upgrade() -> None:
    op.create_table(
        "zeitplan_aenderungsantraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("gewuenschter_start_am", sa.Date(), nullable=True),
        sa.Column("gewuenschtes_ende_am", sa.Date(), nullable=True),
        sa.Column("begruendung", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("antwort", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("bearbeitet_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bearbeitet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_zeitplan_aenderungsantraege_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["projekt_id"],
            ["projekte.id"],
            name="fk_zeitplan_aenderungsantraege_projekt_id_projekte",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["projekt_aufgaben.id"],
            name="fk_zeitplan_aenderungsantraege_element_id_projekt_aufgaben",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["erstellt_von"], ["users.id"], name="fk_zeitplan_aenderungsantraege_erstellt_von_users"
        ),
        sa.ForeignKeyConstraint(
            ["bearbeitet_von"], ["users.id"], name="fk_zeitplan_aenderungsantraege_bearbeitet_von_users"
        ),
        sa.CheckConstraint(
            "art IN ('verschieben', 'dauer_aendern', 'problem')", name="ck_zeitplan_aenderungsantraege_art_valid"
        ),
        sa.CheckConstraint(
            "status IN ('offen', 'angenommen', 'abgelehnt', 'zurueckgezogen')",
            name="ck_zeitplan_aenderungsantraege_status_valid",
        ),
    )
    op.create_index("ix_zeitplan_aenderungsantraege_mandant_id", "zeitplan_aenderungsantraege", ["mandant_id"])
    op.create_index("ix_zeitplan_aenderungsantraege_projekt_id", "zeitplan_aenderungsantraege", ["projekt_id"])
    op.create_index("ix_zeitplan_aenderungsantraege_element_id", "zeitplan_aenderungsantraege", ["element_id"])
    op.execute("ALTER TABLE zeitplan_aenderungsantraege ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE zeitplan_aenderungsantraege FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON zeitplan_aenderungsantraege
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

    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_aktion_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_aktion_valid "
        f"CHECK (aktion IN {_AKTIONEN_NEU})"
    )
    op.execute(
        """
        INSERT INTO account_typ_rechte (id, account_typ_id, bereich, aktion, erlaubt)
        SELECT gen_random_uuid(), t.id, 'projekte', a.aktion, true
        FROM account_typen t
        CROSS JOIN (VALUES ('zeitplan_sehen'), ('zeitplan_beantragen')) AS a(aktion)
        WHERE t.name = 'Techniker'
           OR EXISTS (
                SELECT 1 FROM account_typ_rechte r
                WHERE r.account_typ_id = t.id AND r.bereich = 'projekte'
                  AND r.aktion = 'sehen' AND r.erlaubt
           )
        ON CONFLICT (account_typ_id, bereich, aktion) DO UPDATE SET erlaubt = true
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM account_typ_rechte WHERE aktion IN ('zeitplan_sehen', 'zeitplan_beantragen')")
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_aktion_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_aktion_valid "
        f"CHECK (aktion IN {_AKTIONEN_ALT})"
    )
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON zeitplan_aenderungsantraege")
    op.drop_table("zeitplan_aenderungsantraege")
