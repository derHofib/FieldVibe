"""Frei konfigurierbare Menue-Kategorien (Office-Seitenleiste): mandant_admin
kann eigene Kategorien anlegen/umbenennen/sortieren/loeschen und jeden
Menuepunkt (nav_key aus frontend/src/config/navSeiten.ts) einer davon
zuordnen, statt der vier fest verdrahteten Kategorien (Arbeit/Finanzen/
Kommunikation/Verwaltung). nav_zuordnungen verweist auf nav_kategorien mit
ON DELETE RESTRICT -- eine Kategorie mit noch zugeordneten Punkten kann
nicht geloescht werden (siehe app/api/routes/nav_kategorien.py: das PUT
raeumt Zuordnungen vor dem Loeschen ohnehin immer leer, das ist ein
zusaetzliches Sicherheitsnetz, kein normaler Codepfad).

Ein Mandant ohne eigene Zeilen in nav_kategorien hat sich nie mit den
Standard-Kategorien auseinandergesetzt -- das Frontend faellt dann auf die
vier hart codierten Kategorien zurueck (siehe navSeiten.ts), komplett ohne
Netzwerk-Zusatzaufwand.

Revision ID: 0071
Revises: 0070
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071"
down_revision: Union[str, None] = "0070"
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
        "nav_kategorien",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("reihenfolge", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_nav_kategorien_mandant_id_mandanten"),
        sa.UniqueConstraint("mandant_id", "name", name="uq_nav_kategorien_mandant_name"),
    )
    op.execute(
        "CREATE TRIGGER trg_nav_kategorien_updated_at BEFORE UPDATE "
        "ON nav_kategorien FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_nav_kategorien_mandant_id", "nav_kategorien", ["mandant_id"])
    _enable_rls("nav_kategorien")

    op.create_table(
        "nav_zuordnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nav_key", sa.Text(), nullable=False),
        sa.Column("kategorie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_nav_zuordnungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["kategorie_id"], ["nav_kategorien.id"], name="fk_nav_zuordnungen_kategorie_id_nav_kategorien",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("mandant_id", "nav_key", name="uq_nav_zuordnungen_mandant_key"),
    )
    op.create_index("ix_nav_zuordnungen_mandant_id", "nav_zuordnungen", ["mandant_id"])
    op.create_index("ix_nav_zuordnungen_kategorie_id", "nav_zuordnungen", ["kategorie_id"])
    _enable_rls("nav_zuordnungen")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON nav_zuordnungen")
    op.drop_table("nav_zuordnungen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON nav_kategorien")
    op.drop_table("nav_kategorien")
