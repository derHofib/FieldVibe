"""Gantt-Zeitplan fuer Projekte: Phasen, Arbeitsschritte und Meilensteine als
weitere typ-Werte von projekt_aufgaben (Bestand bleibt typ 'aufgabe'), dazu
Ende->Anfang-Abhaengigkeiten und der Verschiebe-Modus am Projekt.

plan_phase_id ist bewusst NICHT eltern_aufgabe_id: Letzteres sind die
bestehenden Unteraufgaben (Detail-Panel der Kanban-Karte), die Zeitplan-
Gruppierung ist davon unabhaengig. art ist schon fuer anfang_anfang/
ende_ende vorbereitet, Phase 1 nutzt nur ende_anfang.

Revision ID: 0091
Revises: 0090
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0091"
down_revision: Union[str, None] = "0090"
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
    op.add_column("projekt_aufgaben", sa.Column("typ", sa.Text(), nullable=False, server_default="aufgabe"))
    op.add_column("projekt_aufgaben", sa.Column("start_am", sa.Date(), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("ende_am", sa.Date(), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("fortschritt", sa.SmallInteger(), nullable=False, server_default="0"))
    op.add_column("projekt_aufgaben", sa.Column("plan_phase_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("plan_reihenfolge", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key(
        "fk_projekt_aufgaben_plan_phase_id_projekt_aufgaben",
        "projekt_aufgaben",
        "projekt_aufgaben",
        ["plan_phase_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_projekt_aufgaben_typ_valid",
        "projekt_aufgaben",
        "typ IN ('aufgabe', 'phase', 'schritt', 'meilenstein')",
    )
    op.create_check_constraint(
        "ck_projekt_aufgaben_zeitraum_valid",
        "projekt_aufgaben",
        "ende_am IS NULL OR start_am IS NULL OR ende_am >= start_am",
    )
    op.create_check_constraint(
        "ck_projekt_aufgaben_meilenstein_eintaegig",
        "projekt_aufgaben",
        "typ <> 'meilenstein' OR start_am IS NULL OR ende_am = start_am",
    )
    op.create_check_constraint(
        "ck_projekt_aufgaben_fortschritt_valid", "projekt_aufgaben", "fortschritt BETWEEN 0 AND 100"
    )
    op.create_index("ix_projekt_aufgaben_projekt_id_typ", "projekt_aufgaben", ["projekt_id", "typ"])

    op.add_column("projekte", sa.Column("verschiebe_modus", sa.Text(), nullable=False, server_default="bei_konflikt"))
    op.create_check_constraint(
        "ck_projekte_verschiebe_modus_valid", "projekte", "verschiebe_modus IN ('bei_konflikt', 'immer')"
    )

    op.create_table(
        "projekt_aufgabe_abhaengigkeiten",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgaenger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nachfolger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("art", sa.Text(), nullable=False, server_default="ende_anfang"),
        sa.Column("versatz_tage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_projekt_abh_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["projekt_id"],
            ["projekte.id"],
            name="fk_projekt_abh_projekt_id_projekte",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vorgaenger_id"],
            ["projekt_aufgaben.id"],
            name="fk_projekt_abh_vorgaenger_id_projekt_aufgaben",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["nachfolger_id"],
            ["projekt_aufgaben.id"],
            name="fk_projekt_abh_nachfolger_id_projekt_aufgaben",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["erstellt_von"], ["users.id"], name="fk_projekt_abh_erstellt_von_users"
        ),
        sa.UniqueConstraint("vorgaenger_id", "nachfolger_id", name="uq_projekt_abh_paar"),
        sa.CheckConstraint(
            "art IN ('ende_anfang', 'anfang_anfang', 'ende_ende')",
            name="ck_projekt_abh_art_valid",
        ),
        sa.CheckConstraint(
            "vorgaenger_id <> nachfolger_id", name="ck_projekt_abh_kein_selbstbezug"
        ),
    )
    op.create_index("ix_projekt_abh_mandant_id", "projekt_aufgabe_abhaengigkeiten", ["mandant_id"])
    op.create_index("ix_projekt_abh_projekt_id", "projekt_aufgabe_abhaengigkeiten", ["projekt_id"])
    op.create_index(
        "ix_projekt_abh_nachfolger_id", "projekt_aufgabe_abhaengigkeiten", ["nachfolger_id"]
    )
    _enable_rls("projekt_aufgabe_abhaengigkeiten")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON projekt_aufgabe_abhaengigkeiten")
    op.drop_table("projekt_aufgabe_abhaengigkeiten")

    op.drop_constraint("ck_projekte_verschiebe_modus_valid", "projekte", type_="check")
    op.drop_column("projekte", "verschiebe_modus")

    op.drop_index("ix_projekt_aufgaben_projekt_id_typ", table_name="projekt_aufgaben")
    for name in (
        "ck_projekt_aufgaben_fortschritt_valid",
        "ck_projekt_aufgaben_meilenstein_eintaegig",
        "ck_projekt_aufgaben_zeitraum_valid",
        "ck_projekt_aufgaben_typ_valid",
    ):
        op.drop_constraint(name, "projekt_aufgaben", type_="check")
    op.drop_constraint("fk_projekt_aufgaben_plan_phase_id_projekt_aufgaben", "projekt_aufgaben", type_="foreignkey")
    for spalte in ("plan_reihenfolge", "plan_phase_id", "fortschritt", "ende_am", "start_am", "typ"):
        op.drop_column("projekt_aufgaben", spalte)
