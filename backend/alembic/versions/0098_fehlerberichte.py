"""In-App-Fehlerberichte + Rechte-Bereich "fehlerberichte".

Revision ID: 0098
Revises: 0097
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BEREICHE_ALT = (
    "'vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
    "'statistik', 'mitarbeiterverwaltung', 'formulare', 'partner', 'projekte'"
)
_BEREICHE_NEU = _BEREICHE_ALT + ", 'fehlerberichte'"


def upgrade() -> None:
    op.create_table(
        "fehlerberichte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("erwartet", sa.Text(), nullable=True),
        sa.Column("schritte", sa.Text(), nullable=True),
        sa.Column("schweregrad", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="neu"),
        sa.Column("kontext", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("screenshot_original_key", sa.Text(), nullable=True),
        sa.Column("screenshot_annotiert_key", sa.Text(), nullable=True),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("app_version", sa.Text(), nullable=True),
        sa.Column("commit_sha", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("duplikat_von_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("loesungsnotiz", sa.Text(), nullable=True),
        sa.Column("fix_commit", sa.Text(), nullable=True),
        sa.Column("fix_pr_url", sa.Text(), nullable=True),
        sa.Column("erledigt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_fehlerberichte_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_fehlerberichte_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["duplikat_von_id"],
            ["fehlerberichte.id"],
            name="fk_fehlerberichte_duplikat_von_id_fehlerberichte",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "schweregrad IN ('niedrig', 'mittel', 'hoch', 'blockierend')",
            name="schweregrad_valid",
        ),
        sa.CheckConstraint(
            "status IN ('neu', 'gesichtet', 'in_arbeit', 'behoben', 'abgelehnt', 'duplikat')",
            name="status_valid",
        ),
    )
    op.create_index("ix_fehlerberichte_mandant_status", "fehlerberichte", ["mandant_id", "status"])
    op.create_index("ix_fehlerberichte_fingerprint", "fehlerberichte", ["fingerprint"])
    op.create_index("ix_fehlerberichte_created_at", "fehlerberichte", ["created_at"])
    op.execute(
        "CREATE TRIGGER trg_fehlerberichte_updated_at BEFORE UPDATE ON fehlerberichte "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE fehlerberichte ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fehlerberichte FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON fehlerberichte
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

    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        f"CHECK (bereich IN ({_BEREICHE_NEU}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute("DELETE FROM account_typ_rechte WHERE bereich = 'fehlerberichte'")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        f"CHECK (bereich IN ({_BEREICHE_ALT}))"
    )
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON fehlerberichte")
    op.drop_table("fehlerberichte")
