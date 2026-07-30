"""Anlagen bekommen einen objekttyp (kundenanlage/fahrzeug/lager/baustelle)
statt ausschliesslich Kundenanlagen zu sein -- interne Objekte (kunde_id
NULL) sind gleichzeitig gueltige Lagerorte. Material-Bestand wandert von
einem einzelnen Material.bestand-Feld in eine Bestand-je-Lagerort-Tabelle
(material_bestand), ergaenzt um ein Bewegungs-Ledger (material_bewegungen)
fuer Wareneingang/Umlagerung/Verwendung/Korrektur. Bestehende Bestaende
werden pro Mandant in ein automatisch angelegtes "Zentrallager" ueberfuehrt.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- anlagen: objekttyp + kunde_id optional -----------------------------
    op.add_column(
        "anlagen",
        sa.Column("objekttyp", sa.Text(), nullable=False, server_default="kundenanlage"),
    )
    op.alter_column("anlagen", "kunde_id", nullable=True)
    op.execute(
        "ALTER TABLE anlagen ADD CONSTRAINT ck_anlagen_objekttyp_valid "
        "CHECK (objekttyp IN ('kundenanlage', 'fahrzeug', 'lager', 'baustelle'))"
    )
    op.execute(
        "ALTER TABLE anlagen ADD CONSTRAINT ck_anlagen_kunde_id_passend_zu_objekttyp "
        "CHECK ((objekttyp = 'kundenanlage' AND kunde_id IS NOT NULL) "
        "OR (objekttyp != 'kundenanlage' AND kunde_id IS NULL))"
    )

    # --- material_bestand (Bestand je Lagerort) -----------------------------
    op.create_table(
        "material_bestand",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lager_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_material_bestand_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["material_id"], ["material.id"], name="fk_material_bestand_material_id_material", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lager_id"], ["anlagen.id"], name="fk_material_bestand_lager_id_anlagen"),
        sa.UniqueConstraint("material_id", "lager_id", name="uq_material_bestand_material_lager"),
        sa.CheckConstraint("menge >= 0", name="ck_material_bestand_menge_nicht_negativ"),
    )
    op.execute(
        "CREATE TRIGGER trg_material_bestand_updated_at BEFORE UPDATE ON material_bestand "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_material_bestand_mandant_id", "material_bestand", ["mandant_id"])
    op.create_index("ix_material_bestand_material_id", "material_bestand", ["material_id"])

    op.execute("ALTER TABLE material_bestand ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE material_bestand FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON material_bestand
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

    # --- material_bewegungen (Buchungs-Ledger) ------------------------------
    op.create_table(
        "material_bewegungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("von_lager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nach_lager_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_material_bewegungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["material_id"], ["material.id"], name="fk_material_bewegungen_material_id_material", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["von_lager_id"], ["anlagen.id"], name="fk_material_bewegungen_von_lager_id_anlagen"),
        sa.ForeignKeyConstraint(["nach_lager_id"], ["anlagen.id"], name="fk_material_bewegungen_nach_lager_id_anlagen"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_material_bewegungen_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_material_bewegungen_erstellt_von_users"),
        sa.CheckConstraint("menge > 0", name="ck_material_bewegungen_menge_positiv"),
        sa.CheckConstraint(
            "typ IN ('eingang', 'umlagerung', 'verwendung', 'korrektur')",
            name="ck_material_bewegungen_typ_valid",
        ),
    )
    op.create_index("ix_material_bewegungen_mandant_id", "material_bewegungen", ["mandant_id"])
    op.create_index("ix_material_bewegungen_material_id", "material_bewegungen", ["material_id"])

    op.execute("ALTER TABLE material_bewegungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE material_bewegungen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON material_bewegungen
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

    # --- Bestehenden Bestand in ein Zentrallager je Mandant ueberfuehren ----
    # Jeder Mandant bekommt automatisch ein "Zentrallager" (objekttyp=lager,
    # kein Kundenbezug) -- der bisherige einzelne Material.bestand landet
    # dort, ohne dass sich am sichtbaren Gesamtbestand etwas aendert.
    op.execute(
        """
        INSERT INTO anlagen (id, mandant_id, kunde_id, objekttyp, bezeichnung, adresse, stammdaten, created_at, updated_at)
        SELECT gen_random_uuid(), id, NULL, 'lager', 'Zentrallager', '{}'::jsonb, '{}'::jsonb, now(), now()
        FROM mandanten
        """
    )
    op.execute(
        """
        INSERT INTO material_bestand (id, mandant_id, material_id, lager_id, menge)
        SELECT gen_random_uuid(), m.mandant_id, m.id, a.id, m.bestand
        FROM material m
        JOIN anlagen a ON a.mandant_id = m.mandant_id AND a.objekttyp = 'lager' AND a.bezeichnung = 'Zentrallager'
        """
    )

    # --- material_verwendungen: Lagerort verpflichtend ergaenzen -----------
    op.add_column(
        "material_verwendungen", sa.Column("lager_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        """
        UPDATE material_verwendungen v
        SET lager_id = a.id
        FROM anlagen a
        WHERE a.mandant_id = v.mandant_id AND a.objekttyp = 'lager' AND a.bezeichnung = 'Zentrallager'
        """
    )
    op.alter_column("material_verwendungen", "lager_id", nullable=False)
    op.create_foreign_key(
        "fk_material_verwendungen_lager_id_anlagen", "material_verwendungen", "anlagen", ["lager_id"], ["id"]
    )

    op.drop_constraint("ck_material_bestand_nicht_negativ", "material", type_="check")
    op.drop_column("material", "bestand")


def downgrade() -> None:
    op.add_column("material", sa.Column("bestand", sa.Numeric(10, 2), nullable=True))
    op.execute(
        """
        UPDATE material m
        SET bestand = COALESCE((SELECT SUM(mb.menge) FROM material_bestand mb WHERE mb.material_id = m.id), 0)
        """
    )
    op.alter_column("material", "bestand", nullable=False, server_default="0")
    op.create_check_constraint("ck_material_bestand_nicht_negativ", "material", "bestand >= 0")

    op.drop_constraint("fk_material_verwendungen_lager_id_anlagen", "material_verwendungen", type_="foreignkey")
    op.drop_column("material_verwendungen", "lager_id")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON material_bewegungen")
    op.drop_table("material_bewegungen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON material_bestand")
    op.drop_table("material_bestand")

    # Nur die in dieser Migration automatisch angelegten Zentrallager wieder
    # entfernen -- danach zusaetzlich vom Nutzer angelegte Fahrzeug-/Lager-
    # Anlagen (kunde_id weiterhin NULL) lassen sich mit dem alten Schema
    # nicht mehr abbilden und blockieren den naechsten Schritt bewusst mit
    # einem klaren NOT-NULL-Fehler, statt sie stillschweigend zu loeschen.
    op.execute("DELETE FROM anlagen WHERE objekttyp = 'lager' AND bezeichnung = 'Zentrallager'")

    op.execute("ALTER TABLE anlagen DROP CONSTRAINT ck_anlagen_kunde_id_passend_zu_objekttyp")
    op.execute("ALTER TABLE anlagen DROP CONSTRAINT ck_anlagen_objekttyp_valid")
    op.alter_column("anlagen", "kunde_id", nullable=False)
    op.drop_column("anlagen", "objekttyp")
