"""Abwesenheitsantraege, Urlaubsanspruch, Kategorie freizeitausgleich
(docs/konzepte/ZEITERFASSUNG.md, Abschnitt "Abwesenheiten, Urlaubskonto,
Freizeitausgleich").

Revision ID: 0101
Revises: 0100
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0101"
down_revision: Union[str, None] = "0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KATEGORIEN_ALT = (
    "'auftrag', 'verwaltung', 'fahrzeit', 'schulung', 'pause', 'urlaub', 'krankheit', 'sonstiges'"
)
_KATEGORIEN_NEU = (
    "'auftrag', 'verwaltung', 'fahrzeit', 'schulung', 'pause', 'urlaub', 'krankheit', "
    "'freizeitausgleich', 'sonstiges'"
)


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


def _kategorie_check(werte: str) -> None:
    op.execute("ALTER TABLE zeiterfassung DROP CONSTRAINT ck_zeiterfassung_kategorie_valid")
    op.execute(
        f"ALTER TABLE zeiterfassung ADD CONSTRAINT ck_zeiterfassung_kategorie_valid CHECK (kategorie IN ({werte}))"
    )


def upgrade() -> None:
    op.create_table(
        "abwesenheitsantraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("von", sa.Date(), nullable=False),
        sa.Column("bis", sa.Date(), nullable=False),
        sa.Column("halber_tag_von", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("halber_tag_bis", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("antwort", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("bearbeitet_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bearbeitet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_abwesenheitsantraege_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_abwesenheitsantraege_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_abwesenheitsantraege_erstellt_von_users"),
        sa.ForeignKeyConstraint(["bearbeitet_von"], ["users.id"], name="fk_abwesenheitsantraege_bearbeitet_von_users"),
        sa.CheckConstraint(
            "art IN ('urlaub', 'krankheit', 'freizeitausgleich')", name="ck_abwesenheitsantraege_art_valid"
        ),
        sa.CheckConstraint(
            "status IN ('offen', 'genehmigt', 'abgelehnt', 'zurueckgezogen')",
            name="ck_abwesenheitsantraege_status_valid",
        ),
        sa.CheckConstraint("bis >= von", name="ck_abwesenheitsantraege_zeitraum_valid"),
    )
    op.create_index("ix_abwesenheitsantraege_mandant_id", "abwesenheitsantraege", ["mandant_id"])
    op.create_index("ix_abwesenheitsantraege_user_von", "abwesenheitsantraege", ["mandant_id", "user_id", "von"])
    _enable_rls("abwesenheitsantraege")

    op.create_table(
        "urlaubsanspruch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jahr", sa.Integer(), nullable=False),
        sa.Column("tage", sa.Numeric(5, 1), nullable=False),
        sa.Column("resturlaub_tage", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("resturlaub_verfaellt_am", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_urlaubsanspruch_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_urlaubsanspruch_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("mandant_id", "user_id", "jahr", name="uq_urlaubsanspruch_user_jahr"),
        sa.CheckConstraint("tage >= 0 AND resturlaub_tage >= 0", name="ck_urlaubsanspruch_tage_valid"),
    )
    op.create_index("ix_urlaubsanspruch_mandant_id", "urlaubsanspruch", ["mandant_id"])
    _enable_rls("urlaubsanspruch")

    # SET NULL: Antraege werden nie geloescht (nur Status), aber falls doch
    # (z. B. Aufraeumen), sollen die Zeiteintraege als Historie bestehen bleiben.
    op.add_column("zeiterfassung", sa.Column("abwesenheit_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_zeiterfassung_abwesenheit_id_abwesenheitsantraege",
        "zeiterfassung",
        "abwesenheitsantraege",
        ["abwesenheit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_zeiterfassung_abwesenheit_id", "zeiterfassung", ["abwesenheit_id"])
    _kategorie_check(_KATEGORIEN_NEU)


def downgrade() -> None:
    op.execute("DELETE FROM zeiterfassung WHERE kategorie = 'freizeitausgleich'")
    _kategorie_check(_KATEGORIEN_ALT)
    op.drop_index("ix_zeiterfassung_abwesenheit_id", table_name="zeiterfassung")
    op.drop_constraint("fk_zeiterfassung_abwesenheit_id_abwesenheitsantraege", "zeiterfassung", type_="foreignkey")
    op.drop_column("zeiterfassung", "abwesenheit_id")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON urlaubsanspruch")
    op.drop_table("urlaubsanspruch")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON abwesenheitsantraege")
    op.drop_table("abwesenheitsantraege")
