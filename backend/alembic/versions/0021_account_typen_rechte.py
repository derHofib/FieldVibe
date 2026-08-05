"""Zwei weitere Account-Typen (controller, mitarbeiter) sowie eine pro
Mandant konfigurierbare Rechte-Matrix, mit der ein mandant_admin einstellen
kann, was diese beiden Account-Typen je Funktionsbereich sehen/bearbeiten
duerfen (siehe app/services/rechte_service.py).

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-01
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
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_valid")
    # 0001 declared this CHECK inline via sa.CheckConstraint(name=...) inside
    # op.create_table(); with this project's "ck": "ck_%(table_name)s_%(constraint_name)s"
    # naming convention (app/db/base.py) bound as Alembic's target_metadata,
    # that inline form gets the convention applied a second time on top of
    # the already-fully-qualified literal name, silently leaving a second,
    # doubled-prefix duplicate of the constraint (ck_users_ck_users_role_valid)
    # alongside the correctly-named one. Harmless while both enforce the same
    # values, but it would otherwise keep rejecting the new roles below even
    # after the statement above updates the correctly-named constraint.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_ck_users_role_valid")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role_valid "
        "CHECK (role IN ('super_admin','mandant_admin','disponent','techniker',"
        "'controller','mitarbeiter'))"
    )

    op.create_table(
        "mandant_rollen_rechte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("bereich", sa.Text(), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("erlaubt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_mandant_rollen_rechte_mandant_id_mandanten"
        ),
        sa.UniqueConstraint(
            "mandant_id", "rolle", "bereich", "aktion", name="uq_mandant_rollen_rechte"
        ),
        sa.CheckConstraint("rolle IN ('controller', 'mitarbeiter')", name="ck_mandant_rollen_rechte_rolle_valid"),
        sa.CheckConstraint(
            "bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
            "'statistik', 'mitarbeiterverwaltung')",
            name="ck_mandant_rollen_rechte_bereich_valid",
        ),
        sa.CheckConstraint("aktion IN ('sehen', 'bearbeiten')", name="ck_mandant_rollen_rechte_aktion_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_mandant_rollen_rechte_updated_at BEFORE UPDATE ON mandant_rollen_rechte "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_mandant_rollen_rechte_mandant_id", "mandant_rollen_rechte", ["mandant_id"])

    op.execute("ALTER TABLE mandant_rollen_rechte ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mandant_rollen_rechte FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON mandant_rollen_rechte
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
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mandant_rollen_rechte")
    op.drop_table("mandant_rollen_rechte")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_valid")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role_valid "
        "CHECK (role IN ('super_admin','mandant_admin','disponent','techniker'))"
    )
