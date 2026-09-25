"""Auftrag: neue Zwischenebene zwischen Projekt und Vorgang. Projekt --*
Auftrag --* Vorgang, wobei jede Ebene unabhaengig und rein referenziell
verknuepft ist -- ein Vorgang kann weiterhin auch ohne Auftrag direkt an
einem Projekt haengen (Vorgang.projekt_id aus Migration 0082 bleibt
unveraendert bestehen), und ein Auftrag kann ohne Projekt existieren.
Kein Status-Sync in irgendeine Richtung, gleiches Prinzip wie
Projekt.vertrag_id/Vorgang.projekt_id.

Nutzt bewusst den bestehenden Rechte-Bereich "projekte" statt eines
eigenen -- keine Aenderung an der account_typ_rechte-CHECK-Constraint
noetig (siehe app/models/auftrag.py fuer die Begruendung).

Revision ID: 0083
Revises: 0082
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0083"
down_revision: Union[str, None] = "0082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.create_table(
        "auftraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_auftraege_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["projekt_id"], ["projekte.id"], name="fk_auftraege_projekt_id_projekte"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_auftraege_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_auftraege_erstellt_von_users"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_auftraege_geloescht_von_users"),
        sa.CheckConstraint(
            "status IN ('offen', 'in_arbeit', 'abgeschlossen', 'storniert')",
            name="ck_auftraege_status_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_auftraege_updated_at BEFORE UPDATE "
        "ON auftraege FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_auftraege_mandant_id", "auftraege", ["mandant_id"])
    op.create_index("ix_auftraege_projekt_id", "auftraege", ["projekt_id"])
    op.create_index("ix_auftraege_kunde_id", "auftraege", ["kunde_id"])
    _enable_rls("auftraege")

    op.add_column("vorgaenge", sa.Column("auftrag_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_vorgaenge_auftrag_id_auftraege", "vorgaenge", "auftraege", ["auftrag_id"], ["id"]
    )
    op.create_index("ix_vorgaenge_auftrag_id", "vorgaenge", ["auftrag_id"])


def downgrade() -> None:
    op.drop_index("ix_vorgaenge_auftrag_id", table_name="vorgaenge")
    op.drop_constraint("fk_vorgaenge_auftrag_id_auftraege", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "auftrag_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON auftraege")
    op.drop_table("auftraege")
