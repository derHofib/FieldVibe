"""Projekt-Management-Anbindung an Vorgang: das bestehende (bisher bewusst
Vorgang-unabhaengige) Kanban-Projekt bekommt einen optionalen Vertrag-Bezug,
Vorgang bekommt einen optionalen Projekt-Bezug (rein referenziell, kein
Status-Sync -- gleiches Prinzip wie ProjektAufgabe.vorgang_id, siehe
app/models/projekt.py). Subtasks (Vorgang.parent_vorgang_id) existieren
bereits seit Vorgang v1 und sind hier nicht Teil der Migration.

Neue Tabelle vorgang_abhaengigkeiten fuer "blockiert von"-Beziehungen
zwischen Vorgaengen (z.B. Teilleistung B kann erst starten, wenn Teilleistung
A abgeschlossen ist). Zyklen werden applikationsseitig geprueft (siehe
app/api/routes/vorgaenge.py), nicht per DB-Constraint -- ein A->B->A-Zyklus
laesst sich nicht als einfacher CHECK ausdruecken.

Revision ID: 0082
Revises: 0081
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0082"
down_revision: Union[str, None] = "0081"
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
    op.add_column("projekte", sa.Column("vertrag_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projekte_vertrag_id_vertraege", "projekte", "vertraege", ["vertrag_id"], ["id"]
    )
    op.create_index("ix_projekte_vertrag_id", "projekte", ["vertrag_id"])

    op.add_column("vorgaenge", sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_vorgaenge_projekt_id_projekte", "vorgaenge", "projekte", ["projekt_id"], ["id"]
    )
    op.create_index("ix_vorgaenge_projekt_id", "vorgaenge", ["projekt_id"])

    op.create_table(
        "vorgang_abhaengigkeiten",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blockiert_von_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vorgang_abhaengigkeiten_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_vorgang_abhaengigkeiten_vorgang_id_vorgaenge", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["blockiert_von_id"],
            ["vorgaenge.id"],
            name="fk_vorgang_abhaengigkeiten_blockiert_von_id_vorgaenge",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_vorgang_abhaengigkeiten_erstellt_von_users"),
        sa.CheckConstraint("vorgang_id <> blockiert_von_id", name="ck_vorgang_abhaengigkeiten_nicht_selbst"),
        sa.UniqueConstraint("vorgang_id", "blockiert_von_id", name="uq_vorgang_abhaengigkeiten_paar"),
    )
    op.create_index("ix_vorgang_abhaengigkeiten_mandant_id", "vorgang_abhaengigkeiten", ["mandant_id"])
    op.create_index("ix_vorgang_abhaengigkeiten_blockiert_von_id", "vorgang_abhaengigkeiten", ["blockiert_von_id"])
    _enable_rls("vorgang_abhaengigkeiten")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vorgang_abhaengigkeiten")
    op.drop_table("vorgang_abhaengigkeiten")

    op.drop_index("ix_vorgaenge_projekt_id", table_name="vorgaenge")
    op.drop_constraint("fk_vorgaenge_projekt_id_projekte", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "projekt_id")

    op.drop_index("ix_projekte_vertrag_id", table_name="projekte")
    op.drop_constraint("fk_projekte_vertrag_id_vertraege", "projekte", type_="foreignkey")
    op.drop_column("projekte", "vertrag_id")
