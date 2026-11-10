"""Leistungsverzeichnis-Umbau: Container-Entitaet statt loser Positionen.

Bisher hatte jede LeistungsverzeichnisPosition ihre eigene, optionale
Kunden-Zuweisung (leistungsverzeichnis_position_kunden). Neu: Positionen
gehoeren zu einem Leistungsverzeichnis (Kopf-Entitaet), und die
Kunden-Zuweisung sitzt nur noch dort (leistungsverzeichnis_kunden, M:N) --
ein LV kann mehreren Kunden zugeordnet sein, eine leere Zuordnung gilt
weiterhin "fuer alle Kunden". Das erlaubt das gezielte "Duplizieren" eines
kompletten LV samt Positionen fuer einen anderen Kunden.

Backfill (bewusst verlustbehaftet/konsolidierend, siehe Absprache mit dem
Nutzer): je Mandant werden alle bestehenden Positionen in ein einziges neu
angelegtes "Allgemeines Leistungsverzeichnis" uebernommen; diesem LV wird
die Vereinigungsmenge aller Kunden zugewiesen, die zuvor irgendeiner seiner
Positionen zugewiesen waren. Das bildet die alte "Position -> Kunde X oder
Kunde Y"-Streuung nicht mehr 1:1 ab (die alte Kunden-Praezision pro
Einzelposition geht verloren), das wurde jedoch als handhabbare
Vereinfachung akzeptiert.

Zusaetzlich (zweiter, unabhaengiger Teil derselben Absprache): zwei neue
Prozentsatz-Felder je Position fuer eine realistischere
Preisfindung -- lohn_gemeinkosten_prozent (Aufschlag auf den Lohnanteil,
Pendant zu material_aufschlag_prozent auf der Materialseite) und
gewinn_wagnis_prozent (zweite Marge-Schicht auf die Gesamt-Zwischensumme
aus Lohn+Material), siehe app/models/leistungsverzeichnis.py sowie zwei
neue Mandant-Vorbelegungsfelder dafuer.

Revision ID: 0079
Revises: 0078
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "0079"
down_revision: Union[str, None] = "0078"
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
    conn = op.get_bind()

    # --- leistungsverzeichnisse ------------------------------------------
    op.create_table(
        "leistungsverzeichnisse",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("geloescht_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geloescht_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_leistungsverzeichnisse_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["geloescht_von"], ["users.id"], name="fk_leistungsverzeichnisse_geloescht_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_leistungsverzeichnisse_updated_at BEFORE UPDATE ON leistungsverzeichnisse "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_leistungsverzeichnisse_mandant_id", "leistungsverzeichnisse", ["mandant_id"])
    _enable_rls("leistungsverzeichnisse")

    # --- leistungsverzeichnis_kunden --------------------------------------
    op.create_table(
        "leistungsverzeichnis_kunden",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leistungsverzeichnis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_leistungsverzeichnis_kunden_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["leistungsverzeichnis_id"],
            ["leistungsverzeichnisse.id"],
            name="fk_leistungsverzeichnis_kunden_lv_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["kunde_id"], ["kunden.id"], name="fk_leistungsverzeichnis_kunden_kunde_id_kunden", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("leistungsverzeichnis_id", "kunde_id", name="uq_leistungsverzeichnis_kunden_lv_kunde"),
    )
    op.create_index("ix_leistungsverzeichnis_kunden_mandant_id", "leistungsverzeichnis_kunden", ["mandant_id"])
    op.create_index(
        "ix_leistungsverzeichnis_kunden_leistungsverzeichnis_id", "leistungsverzeichnis_kunden", ["leistungsverzeichnis_id"]
    )
    _enable_rls("leistungsverzeichnis_kunden")

    # --- leistungsverzeichnis_positionen: neue Spalten --------------------
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("leistungsverzeichnis_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("lohn_gemeinkosten_prozent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "leistungsverzeichnis_positionen",
        sa.Column("gewinn_wagnis_prozent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )

    # --- mandanten: neue Vorbelegungs-Defaults ----------------------------
    op.add_column(
        "mandanten",
        sa.Column("standard_lohn_gemeinkosten_prozent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "mandanten",
        sa.Column("standard_gewinn_wagnis_prozent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )

    # --- Backfill: ein "Allgemeines Leistungsverzeichnis" je Mandant mit
    # bestehenden Positionen, Kunden-Zuweisung = Vereinigungsmenge der
    # bisher irgendeiner seiner Positionen zugewiesenen Kunden. -----------
    mandanten_mit_positionen = conn.execute(
        text("SELECT DISTINCT mandant_id FROM leistungsverzeichnis_positionen")
    ).scalars().all()

    for mandant_id in mandanten_mit_positionen:
        lv_id = conn.execute(
            text(
                "INSERT INTO leistungsverzeichnisse (id, mandant_id, name, beschreibung) "
                "VALUES (gen_random_uuid(), :mandant_id, 'Allgemeines Leistungsverzeichnis', "
                "'Automatisch beim Umbau auf Leistungsverzeichnis-Container aus den bestehenden "
                "Positionen dieses Mandanten zusammengefasst.') RETURNING id"
            ),
            {"mandant_id": mandant_id},
        ).scalar_one()

        conn.execute(
            text(
                "UPDATE leistungsverzeichnis_positionen SET leistungsverzeichnis_id = :lv_id "
                "WHERE mandant_id = :mandant_id"
            ),
            {"lv_id": lv_id, "mandant_id": mandant_id},
        )

        kunden_ids = conn.execute(
            text(
                "SELECT DISTINCT lpk.kunde_id FROM leistungsverzeichnis_position_kunden lpk "
                "JOIN leistungsverzeichnis_positionen lp ON lp.id = lpk.lv_position_id "
                "WHERE lp.mandant_id = :mandant_id"
            ),
            {"mandant_id": mandant_id},
        ).scalars().all()
        for kunde_id in kunden_ids:
            conn.execute(
                text(
                    "INSERT INTO leistungsverzeichnis_kunden (id, mandant_id, leistungsverzeichnis_id, kunde_id) "
                    "VALUES (gen_random_uuid(), :mandant_id, :lv_id, :kunde_id)"
                ),
                {"mandant_id": mandant_id, "lv_id": lv_id, "kunde_id": kunde_id},
            )

    op.alter_column("leistungsverzeichnis_positionen", "leistungsverzeichnis_id", nullable=False)
    op.create_foreign_key(
        "fk_leistungsverzeichnis_positionen_lv_id",
        "leistungsverzeichnis_positionen",
        "leistungsverzeichnisse",
        ["leistungsverzeichnis_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_leistungsverzeichnis_positionen_leistungsverzeichnis_id",
        "leistungsverzeichnis_positionen",
        ["leistungsverzeichnis_id"],
    )

    # --- Alt-Tabelle entfernen ---------------------------------------------
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON leistungsverzeichnis_position_kunden")
    op.drop_table("leistungsverzeichnis_position_kunden")


def downgrade() -> None:
    raise RuntimeError(
        "Kein Downgrade-Pfad: der Backfill fasst bestehende Positionen konsolidiert in ein "
        "gemeinsames LV zusammen und die urspruengliche Position-zu-Kunde-Zuordnung ist danach "
        "nicht mehr rekonstruierbar. Ein Restore aus einem Datenbank-Backup vor dieser Migration "
        "ist der einzige Weg zurueck."
    )
