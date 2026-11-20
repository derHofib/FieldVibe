"""Kontakte vor Ort (Kunden des Kunden), Etappe A.

Personen auf der Seite von A's Kunden (Mieter, Eigentuemer, Bauherr, Hausmeister), die der Techniker
vor Ort erreichen muss. Bewusst keine Kunden (kein Debitor/Portal), sondern eine eigene schlanke
Tabelle unter dem Auftraggeber, optional an einer Liegenschaft (Standort).

- vor_ort_kontakte: RLS-Policy + FORCE + updated_at-Trigger nach Repo-Konvention.
- vor_ort_kontakt_zuordnungen: Kontakt <-> Projekt/Auftrag/Vorgang (drei FK-Spalten statt
  polymorphem Ziel, damit Postgres die Referenzen prueft und Loeschen kaskadiert).
- auftraege: standort_id, einheit, ansprechpartner_id (kein FK, Id aus kunden.ansprechpartner),
  kunden_referenz.
- projekte: kunde_id, standort_id.
- vorgaenge: einheit.
- mandanten: vor_ort_kontakte_anonymisieren_monate.

Kein Backfill: alles ist neu und nullable.

Revision ID: 0125
Revises: 0124
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0125"
down_revision: Union[str, None] = "0124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLLEN = ("mieter", "eigentuemer", "bauherr", "hausmeister", "nutzer", "sonstige")
_QUELLEN = ("buero", "kundenportal", "telefonat")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        WITH CHECK (mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid)
        """
    )


def upgrade() -> None:
    op.create_table(
        "vor_ort_kontakte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("einheit", sa.Text(), nullable=True),
        sa.Column("telefon", sa.Text(), nullable=True),
        sa.Column("telefon2", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("erreichbarkeit", sa.Text(), nullable=True),
        sa.Column("hinweis", sa.Text(), nullable=True),
        # Art. 14 DSGVO: woher die Daten stammen.
        sa.Column("quelle", sa.Text(), nullable=True),
        sa.Column("letzter_einsatz_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("anonymisiert_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von_kundenportal_zugang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("geloescht_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vor_ort_kontakte_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_vor_ort_kontakte_kunde_id_kunden"),
        sa.ForeignKeyConstraint(
            ["standort_id"], ["standorte.id"], name="fk_vor_ort_kontakte_standort_id_standorte", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_vor_ort_kontakte_erstellt_von_users"),
        sa.ForeignKeyConstraint(
            ["erstellt_von_kundenportal_zugang_id"],
            ["kundenportal_zugaenge.id"],
            name="fk_vor_ort_kontakte_portal_zugang_kundenportal_zugaenge",
        ),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_vor_ort_kontakte_geloescht_von_users"),
        sa.CheckConstraint(f"rolle IN {_ROLLEN}", name="rolle_valid"),
        sa.CheckConstraint(f"quelle IS NULL OR quelle IN {_QUELLEN}", name="quelle_valid"),
        sa.CheckConstraint(
            "anonymisiert_am IS NOT NULL OR name IS NOT NULL OR telefon IS NOT NULL",
            name="name_oder_telefon",
        ),
    )
    op.create_index("ix_vor_ort_kontakte_mandant_kunde_standort", "vor_ort_kontakte", ["mandant_id", "kunde_id", "standort_id"])
    op.execute(
        "CREATE TRIGGER trg_vor_ort_kontakte_updated_at BEFORE UPDATE ON vor_ort_kontakte "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _enable_rls("vor_ort_kontakte")

    op.create_table(
        "vor_ort_kontakt_zuordnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kontakt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("auftrag_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ist_hauptkontakt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_vor_ort_kontakt_zuordnungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["kontakt_id"], ["vor_ort_kontakte.id"],
            name="fk_vor_ort_kontakt_zuordnungen_kontakt_id_vor_ort_kontakte", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["projekt_id"], ["projekte.id"],
            name="fk_vor_ort_kontakt_zuordnungen_projekt_id_projekte", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["auftrag_id"], ["auftraege.id"],
            name="fk_vor_ort_kontakt_zuordnungen_auftrag_id_auftraege", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"],
            name="fk_vor_ort_kontakt_zuordnungen_vorgang_id_vorgaenge", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["erstellt_von"], ["users.id"], name="fk_vor_ort_kontakt_zuordnungen_erstellt_von_users"
        ),
        sa.CheckConstraint(
            "num_nonnulls(projekt_id, auftrag_id, vorgang_id) = 1", name="genau_ein_ziel"
        ),
    )
    for ziel in ("projekt_id", "auftrag_id", "vorgang_id"):
        op.create_index(f"ix_vor_ort_kontakt_zuordnungen_{ziel}", "vor_ort_kontakt_zuordnungen", [ziel])
        op.create_index(
            f"uq_vor_ort_kontakt_zuordnungen_kontakt_{ziel}",
            "vor_ort_kontakt_zuordnungen",
            ["kontakt_id", ziel],
            unique=True,
            postgresql_where=sa.text(f"{ziel} IS NOT NULL"),
        )
        # Hoechstens ein Hauptkontakt je Ziel, auch gegen konkurrierende Requests (Muster 0124).
        op.create_index(
            f"uq_vor_ort_kontakt_zuordnungen_haupt_{ziel}",
            "vor_ort_kontakt_zuordnungen",
            [ziel],
            unique=True,
            postgresql_where=sa.text(f"ist_hauptkontakt AND {ziel} IS NOT NULL"),
        )
    op.create_index("ix_vor_ort_kontakt_zuordnungen_kontakt_id", "vor_ort_kontakt_zuordnungen", ["kontakt_id"])
    _enable_rls("vor_ort_kontakt_zuordnungen")

    op.add_column(
        "auftraege",
        sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_auftraege_standort_id_standorte", "auftraege", "standorte", ["standort_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("auftraege", sa.Column("einheit", sa.Text(), nullable=True))
    # Kein FK: Id aus der JSONB-Liste kunden.ansprechpartner (Muster telefonate.ansprechpartner_id).
    op.add_column("auftraege", sa.Column("ansprechpartner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("auftraege", sa.Column("kunden_referenz", sa.Text(), nullable=True))

    op.add_column("projekte", sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_projekte_kunde_id_kunden", "projekte", "kunden", ["kunde_id"], ["id"])
    op.add_column("projekte", sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projekte_standort_id_standorte", "projekte", "standorte", ["standort_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("vorgaenge", sa.Column("einheit", sa.Text(), nullable=True))

    op.add_column(
        "mandanten",
        sa.Column("vor_ort_kontakte_anonymisieren_monate", sa.SmallInteger(), nullable=False, server_default="12"),
    )
    op.create_check_constraint(
        "vor_ort_anonymisieren_monate_valid",
        "mandanten",
        "vor_ort_kontakte_anonymisieren_monate BETWEEN 3 AND 60",
    )


def downgrade() -> None:
    op.drop_constraint("vor_ort_anonymisieren_monate_valid", "mandanten", type_="check")
    op.drop_column("mandanten", "vor_ort_kontakte_anonymisieren_monate")

    op.drop_column("vorgaenge", "einheit")

    op.drop_constraint("fk_projekte_standort_id_standorte", "projekte", type_="foreignkey")
    op.drop_column("projekte", "standort_id")
    op.drop_constraint("fk_projekte_kunde_id_kunden", "projekte", type_="foreignkey")
    op.drop_column("projekte", "kunde_id")

    op.drop_column("auftraege", "kunden_referenz")
    op.drop_column("auftraege", "ansprechpartner_id")
    op.drop_column("auftraege", "einheit")
    op.drop_constraint("fk_auftraege_standort_id_standorte", "auftraege", type_="foreignkey")
    op.drop_column("auftraege", "standort_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vor_ort_kontakt_zuordnungen")
    op.drop_table("vor_ort_kontakt_zuordnungen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vor_ort_kontakte")
    op.drop_table("vor_ort_kontakte")
