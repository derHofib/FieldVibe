"""Formular-Baukasten: Raster-Layout (Colspan/Rowspan-Positionierung statt
linearer Liste) + optionale Auto-Fill-Datenquelle je Feld.

Bestehende Felder werden per Backfill als vollbreite, gestapelte Zeilen in
ihrer alten reihenfolge platziert -- der Canvas-Editor zeigt sie dadurch
zunaechst optisch identisch zur bisherigen Liste, bis der Nutzer sie
umgestaltet.

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORMULARFELD_DATENQUELLEN = (
    "vorgang.vorgangsnummer",
    "vorgang.titel",
    "vorgang.beschreibung",
    "vorgang.leistungstyp",
    "vorgang.faelligkeit_am",
    "vorgang.adresse",
    "vorgang.zugewiesener_name",
    "kunde.kundennummer",
    "kunde.name",
    "kunde.adresse",
    "kunde.ansprechpartner",
    "anlage.bezeichnung",
    "anlage.adresse",
    "anlage.hersteller",
    "anlage.modell",
    "anlage.seriennummer",
    "anlage.anlagentyp",
    "standort.bezeichnung",
    "standort.adresse",
)


def upgrade() -> None:
    # --- formulare: Zeilenhoehe --------------------------------------------
    op.add_column(
        "formulare",
        sa.Column("zeilenhoehe_mm", sa.SmallInteger(), nullable=False, server_default="8"),
    )
    op.create_check_constraint(
        "zeilenhoehe_valid", "formulare", "zeilenhoehe_mm BETWEEN 4 AND 20"
    )

    # --- formularfelder: Rasterposition + Datenquelle ----------------------
    op.add_column("formularfelder", sa.Column("raster_zeile", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_spalte", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_breite", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_hoehe", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("datenquelle", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE formularfelder
        SET raster_zeile = reihenfolge, raster_spalte = 0, raster_breite = 12, raster_hoehe = 1
        """
    )

    op.alter_column("formularfelder", "raster_zeile", nullable=False, server_default="0")
    op.alter_column("formularfelder", "raster_spalte", nullable=False, server_default="0")
    op.alter_column("formularfelder", "raster_breite", nullable=False, server_default="12")
    op.alter_column("formularfelder", "raster_hoehe", nullable=False, server_default="1")

    op.create_check_constraint(
        "raster_spalte_valid", "formularfelder", "raster_spalte BETWEEN 0 AND 11"
    )
    op.create_check_constraint(
        "raster_breite_valid", "formularfelder", "raster_breite BETWEEN 1 AND 12"
    )
    op.create_check_constraint(
        "raster_hoehe_valid", "formularfelder", "raster_hoehe >= 1"
    )
    op.create_check_constraint(
        "raster_passt_in_zeile",
        "formularfelder",
        "raster_spalte + raster_breite <= 12",
    )
    op.create_check_constraint(
        "datenquelle_valid",
        "formularfelder",
        f"datenquelle IS NULL OR datenquelle IN {FORMULARFELD_DATENQUELLEN}",
    )


def downgrade() -> None:
    op.drop_constraint("datenquelle_valid", "formularfelder", type_="check")
    op.drop_constraint("raster_passt_in_zeile", "formularfelder", type_="check")
    op.drop_constraint("raster_hoehe_valid", "formularfelder", type_="check")
    op.drop_constraint("raster_breite_valid", "formularfelder", type_="check")
    op.drop_constraint("raster_spalte_valid", "formularfelder", type_="check")
    op.drop_column("formularfelder", "datenquelle")
    op.drop_column("formularfelder", "raster_hoehe")
    op.drop_column("formularfelder", "raster_breite")
    op.drop_column("formularfelder", "raster_spalte")
    op.drop_column("formularfelder", "raster_zeile")

    op.drop_constraint("zeilenhoehe_valid", "formulare", type_="check")
    op.drop_column("formulare", "zeilenhoehe_mm")
