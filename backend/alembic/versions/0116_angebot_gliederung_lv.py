"""angebot_positionen: Gliederung (Titelzeilen), Lohn-/Materialanteil, LV-Herkunft.

Titel sind normale Zeilen mit zeilentyp "titel" (Menge/Preis 0), damit Umordnen,
Nummerierung und die Annahme-Fassung unveraendert mit einer Liste auskommen.
Ordnungszahlen und Zwischensummen werden nicht gespeichert, sondern berechnet.
einzelpreis bleibt die Summe aus Lohn- und Materialanteil (CHECK), Altzeilen
haben beide Anteile NULL. lv_position_id ist nur die Herkunft (SET NULL), der
Preis wird beim Uebernehmen kopiert und aendert sich danach nie mit dem LV.

Die Tabelle hat seit 0006 RLS-Policy und Trigger; neue Spalten brauchen nichts.

Revision ID: 0116
Revises: 0115
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0116"
down_revision: Union[str, None] = "0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "angebot_positionen",
        sa.Column("zeilentyp", sa.Text(), nullable=False, server_default="position"),
    )
    op.add_column(
        "angebot_positionen",
        sa.Column("ebene", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.add_column(
        "angebot_positionen", sa.Column("lv_position_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("angebot_positionen", sa.Column("einzelpreis_lohn", sa.Numeric(10, 2), nullable=True))
    op.add_column("angebot_positionen", sa.Column("einzelpreis_material", sa.Numeric(10, 2), nullable=True))
    op.create_foreign_key(
        "fk_angebot_positionen_lv_position_id_lv_positionen",
        "angebot_positionen",
        "leistungsverzeichnis_positionen",
        ["lv_position_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_angebot_positionen_lv_position_id", "angebot_positionen", ["lv_position_id"])
    op.create_check_constraint(
        "ck_angebot_positionen_zeilentyp_valid", "angebot_positionen", "zeilentyp IN ('position','titel')"
    )
    op.create_check_constraint("ck_angebot_positionen_ebene_valid", "angebot_positionen", "ebene IN (1,2)")
    op.create_check_constraint(
        "ck_angebot_positionen_anteile_summe",
        "angebot_positionen",
        "(einzelpreis_lohn IS NULL AND einzelpreis_material IS NULL)"
        " OR einzelpreis = COALESCE(einzelpreis_lohn, 0) + COALESCE(einzelpreis_material, 0)",
    )


def downgrade() -> None:
    # Titelzeilen waeren ohne die Spalte als 0-Euro-Positionen sichtbar.
    op.execute("DELETE FROM angebot_positionen WHERE zeilentyp = 'titel'")
    op.drop_constraint("ck_angebot_positionen_anteile_summe", "angebot_positionen", type_="check")
    op.drop_constraint("ck_angebot_positionen_ebene_valid", "angebot_positionen", type_="check")
    op.drop_constraint("ck_angebot_positionen_zeilentyp_valid", "angebot_positionen", type_="check")
    op.drop_index("ix_angebot_positionen_lv_position_id", table_name="angebot_positionen")
    op.drop_constraint(
        "fk_angebot_positionen_lv_position_id_lv_positionen", "angebot_positionen", type_="foreignkey"
    )
    op.drop_column("angebot_positionen", "einzelpreis_material")
    op.drop_column("angebot_positionen", "einzelpreis_lohn")
    op.drop_column("angebot_positionen", "lv_position_id")
    op.drop_column("angebot_positionen", "ebene")
    op.drop_column("angebot_positionen", "zeilentyp")
