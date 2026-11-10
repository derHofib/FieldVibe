"""Boards: Miro-artiges Whiteboard fuer die Office-Oberflaeche. Freies Board,
Bauplanung (Grundriss + Pins) und Prozess-Diagramme teilen sich dieselbe
Tabelle -- der komplette Inhalt (Notizen, Formen, Verbindungen, Positionen)
liegt als ein JSON-Baum in inhalt_json, analog zu gespeicherte_filter.
filter_json (0025). Kein Soft-Delete/Papierkorb-Eintrag in v1.

Revision ID: 0067
Revises: 0066
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0067"
down_revision: Union[str, None] = "0066"
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
        "boards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("board_typ", sa.Text(), nullable=False, server_default=sa.text("'frei'")),
        sa.Column("inhalt_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hintergrund_object_key", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_boards_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_boards_erstellt_von_users"),
        sa.CheckConstraint(
            "board_typ IN ('frei', 'bauplanung', 'prozess')",
            name=op.f("ck_boards_board_typ_valid"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_boards_updated_at BEFORE UPDATE ON boards "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_boards_mandant_id", "boards", ["mandant_id"])
    _enable_rls("boards")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON boards")
    op.drop_table("boards")
