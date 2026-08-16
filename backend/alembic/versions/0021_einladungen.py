"""Einladungssystem: statt dass ein Admin direkt einen Account mit
Passwort anlegt, wird eine Einladung per E-Mail verschickt und die
eingeladene Person registriert sich selbst mit eigenem Passwort ueber
einen Einmal-Link. Deckt alle drei Identitaets-Raeume ab
(art='mitarbeiter'/'kunde'/'partner' -- users/kundenportal_zugaenge/
partner_zugaenge werden jeweils erst BEI Annahme der Einladung angelegt,
nicht vorher, brauchen also selbst keine Schema-Aenderung).

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "einladungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("rolle", sa.Text(), nullable=True),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("eingeladen_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("angenommen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_einladungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_einladungen_kunde_id_kunden", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner.id"], name="fk_einladungen_partner_id_partner", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["eingeladen_von"], ["users.id"], name="fk_einladungen_eingeladen_von_users"),
        sa.CheckConstraint("art IN ('mitarbeiter','kunde','partner')", name="ck_einladungen_art_valid"),
        sa.CheckConstraint(
            "rolle IS NULL OR rolle IN ('mandant_admin','disponent','techniker')",
            name="ck_einladungen_rolle_valid",
        ),
        sa.CheckConstraint("status IN ('offen','angenommen','widerrufen')", name="ck_einladungen_status_valid"),
        sa.CheckConstraint(
            "(art = 'mitarbeiter' AND rolle IS NOT NULL AND kunde_id IS NULL AND partner_id IS NULL) OR "
            "(art = 'kunde' AND rolle IS NULL AND kunde_id IS NOT NULL AND partner_id IS NULL) OR "
            "(art = 'partner' AND rolle IS NULL AND kunde_id IS NULL AND partner_id IS NOT NULL)",
            name="ck_einladungen_art_felder_konsistent",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_einladungen_updated_at BEFORE UPDATE ON einladungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_einladungen_mandant_id", "einladungen", ["mandant_id"])
    op.create_index("ix_einladungen_kunde_id", "einladungen", ["kunde_id"])
    op.create_index("ix_einladungen_partner_id", "einladungen", ["partner_id"])
    # Verhindert doppelte gleichzeitig offene Einladungen an dieselbe
    # E-Mail-Adresse innerhalb eines Mandanten (Spam/Verwirrung).
    op.create_index(
        "uq_einladungen_offene_email",
        "einladungen",
        ["mandant_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'offen'"),
    )
    op.execute("ALTER TABLE einladungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE einladungen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON einladungen
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


def downgrade() -> None:
    op.drop_table("einladungen")
