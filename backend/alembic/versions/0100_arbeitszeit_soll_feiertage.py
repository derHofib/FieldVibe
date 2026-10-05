"""Arbeitszeit: Soll-Zeit je Mitarbeiter, Feiertage, Bundesland, Recht
"Abwesenheiten verwalten" (docs/konzepte/ZEITERFASSUNG.md, Abschnitt
"Soll-Zeit, Feiertage, Ueberstundensaldo").

Revision ID: 0100
Revises: 0099
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0100"
down_revision: Union[str, None] = "0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WOCHENTAGE = ("mo", "di", "mi", "do", "fr", "sa", "so")
_BUNDESLAENDER = "('BW','BY','BE','BB','HB','HH','HE','MV','NI','NW','RP','SL','SN','ST','SH','TH')"


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
    op.add_column(
        "account_typen",
        sa.Column("darf_abwesenheiten_verwalten", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("mandanten", sa.Column("bundesland", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_mandanten_bundesland_valid", "mandanten", f"bundesland IS NULL OR bundesland IN {_BUNDESLAENDER}"
    )

    op.create_table(
        "arbeitszeit_soll",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gueltig_ab", sa.Date(), nullable=False),
        *(
            sa.Column(f"stunden_{tag}", sa.Numeric(4, 2), nullable=False, server_default="0")
            for tag in _WOCHENTAGE
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_arbeitszeit_soll_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_arbeitszeit_soll_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("mandant_id", "user_id", "gueltig_ab", name="uq_arbeitszeit_soll_user_gueltig_ab"),
        *(
            sa.CheckConstraint(
                f"stunden_{tag} >= 0 AND stunden_{tag} <= 24", name=f"ck_arbeitszeit_soll_stunden_{tag}_valid"
            )
            for tag in _WOCHENTAGE
        ),
    )
    op.create_index("ix_arbeitszeit_soll_mandant_id", "arbeitszeit_soll", ["mandant_id"])
    op.create_index("ix_arbeitszeit_soll_user_id", "arbeitszeit_soll", ["user_id"])
    _enable_rls("arbeitszeit_soll")

    op.create_table(
        "feiertage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_feiertage_mandant_id_mandanten"),
        sa.UniqueConstraint("mandant_id", "datum", name="uq_feiertage_mandant_datum"),
    )
    op.create_index("ix_feiertage_mandant_id", "feiertage", ["mandant_id"])
    _enable_rls("feiertage")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON feiertage")
    op.drop_table("feiertage")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON arbeitszeit_soll")
    op.drop_table("arbeitszeit_soll")
    op.drop_constraint("ck_mandanten_bundesland_valid", "mandanten", type_="check")
    op.drop_column("mandanten", "bundesland")
    op.drop_column("account_typen", "darf_abwesenheiten_verwalten")
