"""Standort-Ebene zwischen Kunde und Anlage (Kunde -> Standort -> Anlage),
Kundenportal-Auftragsanfragen (Anfrage-Bestaetigung statt direkter
Vorgangsanlage durchs Kundenportal), personalisierter Kundenportal-Login-Link
sowie ein "aktiv"-Flag auf Standort/Anlage, damit inaktive Objekte bei der
Vorgangs-Neuanlage nicht mehr zur Auswahl stehen.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
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
    # --- standorte ------------------------------------------------------
    op.create_table(
        "standorte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("adresse", postgresql.JSONB(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("geo_lat", sa.Float(), nullable=True),
        sa.Column("geo_lng", sa.Float(), nullable=True),
        sa.Column("erstellt_von_kundenportal_zugang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_standorte_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_standorte_kunde_id_kunden"),
        sa.ForeignKeyConstraint(
            ["erstellt_von_kundenportal_zugang_id"],
            ["kundenportal_zugaenge.id"],
            name="fk_standorte_erstellt_von_kundenportal_zugaenge",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_standorte_updated_at BEFORE UPDATE ON standorte "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_standorte_mandant_id", "standorte", ["mandant_id"])
    op.create_index("ix_standorte_kunde_id", "standorte", ["kunde_id"])
    _enable_rls("standorte")

    # --- anlagen: standort_id, aktiv, Kundenportal-Herkunft -----------------
    op.add_column("anlagen", sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "anlagen", sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.add_column(
        "anlagen",
        sa.Column("erstellt_von_kundenportal_zugang_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_anlagen_standort_id_standorte", "anlagen", "standorte", ["standort_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_anlagen_erstellt_von_kundenportal_zugaenge",
        "anlagen",
        "kundenportal_zugaenge",
        ["erstellt_von_kundenportal_zugang_id"],
        ["id"],
    )

    # --- vorgaenge: standort_id, Kundenportal-Ansprechpartner ---------------
    op.add_column("vorgaenge", sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "vorgaenge",
        sa.Column("erstellt_von_kundenportal_zugang_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_vorgaenge_standort_id_standorte", "vorgaenge", "standorte", ["standort_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_vorgaenge_erstellt_von_kundenportal_zugaenge",
        "vorgaenge",
        "kundenportal_zugaenge",
        ["erstellt_von_kundenportal_zugang_id"],
        ["id"],
    )

    # --- kundenportal_zugaenge: personalisierter Login-Link -----------------
    op.add_column("kundenportal_zugaenge", sa.Column("login_slug", sa.Text(), nullable=True))
    op.execute(
        "UPDATE kundenportal_zugaenge SET login_slug = replace(gen_random_uuid()::text, '-', '') "
        "WHERE login_slug IS NULL"
    )
    op.alter_column("kundenportal_zugaenge", "login_slug", nullable=False)
    op.create_unique_constraint(
        "uq_kundenportal_zugaenge_login_slug", "kundenportal_zugaenge", ["login_slug"]
    )

    # --- vorgang_anfragen -----------------------------------------------
    op.create_table(
        "vorgang_anfragen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kundenportal_zugang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("leistungstyp", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("ablehnungsgrund", sa.Text(), nullable=True),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bearbeitet_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bearbeitet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vorgang_anfragen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_vorgang_anfragen_kunde_id_kunden"),
        sa.ForeignKeyConstraint(
            ["kundenportal_zugang_id"],
            ["kundenportal_zugaenge.id"],
            name="fk_vorgang_anfragen_kundenportal_zugang_id",
        ),
        sa.ForeignKeyConstraint(["standort_id"], ["standorte.id"], name="fk_vorgang_anfragen_standort_id_standorte"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_vorgang_anfragen_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_vorgang_anfragen_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["bearbeitet_von"], ["users.id"], name="fk_vorgang_anfragen_bearbeitet_von_users"),
        sa.CheckConstraint(
            "status IN ('offen', 'angenommen', 'abgelehnt')", name="ck_vorgang_anfragen_status_valid"
        ),
        sa.CheckConstraint(
            "leistungstyp IN ('installation', 'pruefung', 'wartung', 'stoerung', 'beratung', 'planung')",
            name="ck_vorgang_anfragen_leistungstyp_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_vorgang_anfragen_updated_at BEFORE UPDATE ON vorgang_anfragen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_vorgang_anfragen_mandant_id", "vorgang_anfragen", ["mandant_id"])
    op.create_index("ix_vorgang_anfragen_kunde_id", "vorgang_anfragen", ["kunde_id"])
    op.create_index("ix_vorgang_anfragen_status", "vorgang_anfragen", ["status"])
    _enable_rls("vorgang_anfragen")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vorgang_anfragen")
    op.drop_table("vorgang_anfragen")

    op.drop_constraint("uq_kundenportal_zugaenge_login_slug", "kundenportal_zugaenge", type_="unique")
    op.drop_column("kundenportal_zugaenge", "login_slug")

    op.drop_constraint("fk_vorgaenge_erstellt_von_kundenportal_zugaenge", "vorgaenge", type_="foreignkey")
    op.drop_constraint("fk_vorgaenge_standort_id_standorte", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "erstellt_von_kundenportal_zugang_id")
    op.drop_column("vorgaenge", "standort_id")

    op.drop_constraint("fk_anlagen_erstellt_von_kundenportal_zugaenge", "anlagen", type_="foreignkey")
    op.drop_constraint("fk_anlagen_standort_id_standorte", "anlagen", type_="foreignkey")
    op.drop_column("anlagen", "erstellt_von_kundenportal_zugang_id")
    op.drop_column("anlagen", "aktiv")
    op.drop_column("anlagen", "standort_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON standorte")
    op.drop_table("standorte")
