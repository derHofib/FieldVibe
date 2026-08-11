"""Formular-Baukasten: freie Positionierung (x_mm/y_mm/breite_mm/hoehe_mm auf
festen A4-Seiten) statt 12-Spalten-Raster -- wie Steuerelemente im
MS-Access-Formular-Designer: beliebige Position/Groesse, ein optionales
Einrastraster (Formular.snap_mm) ist nur eine Editor-Hilfe, keine Struktur-
Zwangsjacke mehr. Ueberlappende Felder sind ab jetzt erlaubt.

Der Backfill spielt die bisherige automatische Seitenumbruch-Entscheidung
aus app/services/pdf_service.py:_generate_formular_pdf_raster exakt nach
(gleiche Kapazitaets-Formel je Seite), damit bereits mehrseitige Formulare
(z.B. ein 41-Zeilen-Pruefprotokoll) nach der Migration weiterhin auf
denselben Seiten mit denselben Positionen erscheinen -- ohne dieses Replay
wuerde alles auf Seite 0 landen und ueber den Seitenrand hinausragen, da das
neue Modell keinen automatischen Umbruch mehr kennt.

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPALTENBREITE_MM = 15.0  # 180mm nutzbare Breite / 12 Spalten (altes Raster)
NUTZBARE_BREITE_MM = 180
RAND_OBEN_SEITE1 = 41  # Briefkopf (Mandant/Formularname/Vorgang/Datum) + Abstand
RAND_OBEN_FOLGESEITE = 22  # schmale Kennzeile ab Seite 2
RAND_UNTEN = 15
SEITENHOEHE_MM = 297


def _kapazitaet(zeilenhoehe_mm: int, ist_erste_seite: bool) -> int:
    rand_oben = RAND_OBEN_SEITE1 if ist_erste_seite else RAND_OBEN_FOLGESEITE
    verfuegbar = SEITENHOEHE_MM - RAND_UNTEN - rand_oben
    return max(int(verfuegbar // zeilenhoehe_mm), 1)


def _replay_seitenumbruch(felder: list[dict], zeilenhoehe_mm: int) -> list[dict]:
    """felder: [{"id":..., "raster_zeile":..., "raster_spalte":..., "raster_breite":...,
    "raster_hoehe":...}], sortiert nach (raster_zeile, raster_spalte). Gibt fuer jedes
    Feld {"id", "seite", "x_mm", "y_mm", "breite_mm", "hoehe_mm"} zurueck -- exakt die
    gleiche Logik wie _generate_formular_pdf_raster, nur ohne PDF-Objekt."""
    ergebnis = []
    seite = 0
    seite_start_zeile = 0
    kapazitaet = _kapazitaet(zeilenhoehe_mm, ist_erste_seite=True)
    for feld in felder:
        lokale_zeile = feld["raster_zeile"] - seite_start_zeile
        if lokale_zeile + feld["raster_hoehe"] > kapazitaet:
            seite += 1
            seite_start_zeile = feld["raster_zeile"]
            kapazitaet = _kapazitaet(zeilenhoehe_mm, ist_erste_seite=False)
            lokale_zeile = 0
        ergebnis.append(
            {
                "id": feld["id"],
                "seite": seite,
                "x_mm": feld["raster_spalte"] * SPALTENBREITE_MM,
                "y_mm": lokale_zeile * zeilenhoehe_mm,
                "breite_mm": feld["raster_breite"] * SPALTENBREITE_MM,
                "hoehe_mm": feld["raster_hoehe"] * zeilenhoehe_mm,
            }
        )
    return ergebnis


def _replay_rueckwaerts(felder: list[dict], zeilenhoehe_mm: int) -> list[dict]:
    """Inverse von _replay_seitenumbruch fuer downgrade() -- rekonstruiert
    raster_zeile als fortlaufenden Zeilenindex ueber alle Seiten hinweg, indem
    die Kapazitaet jeder vorherigen Seite aufsummiert wird. Exakt nur direkt
    nach upgrade() ohne zwischenzeitliche freie Bearbeitung (siehe Modul-
    Docstring) -- ausreichend fuer den ueblichen upgrade/downgrade/upgrade-
    Verifikationszyklus."""
    ergebnis = []
    zeilen_vor_seite: dict[int, int] = {0: 0}
    max_seite = max((f["seite"] for f in felder), default=0)
    kumuliert = 0
    for s in range(1, max_seite + 1):
        kumuliert += _kapazitaet(zeilenhoehe_mm, ist_erste_seite=(s == 1))
        zeilen_vor_seite[s] = kumuliert
    for feld in felder:
        ergebnis.append(
            {
                "id": feld["id"],
                "raster_zeile": zeilen_vor_seite[feld["seite"]] + round(feld["y_mm"] / zeilenhoehe_mm),
                "raster_spalte": round(feld["x_mm"] / SPALTENBREITE_MM),
                "raster_breite": max(round(feld["breite_mm"] / SPALTENBREITE_MM), 1),
                "raster_hoehe": max(round(feld["hoehe_mm"] / zeilenhoehe_mm), 1),
            }
        )
    return ergebnis


def upgrade() -> None:
    bind = op.get_bind()

    # --- formulare: anzahl_seiten + Umbenennung zeilenhoehe_mm -> snap_mm --
    op.add_column(
        "formulare",
        sa.Column("anzahl_seiten", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.create_check_constraint("anzahl_seiten_valid", "formulare", "anzahl_seiten >= 1")

    # --- formularfelder: neue Freiform-Spalten (erst nullable) ------------
    op.add_column("formularfelder", sa.Column("seite", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("x_mm", sa.Float(), nullable=True))
    op.add_column("formularfelder", sa.Column("y_mm", sa.Float(), nullable=True))
    op.add_column("formularfelder", sa.Column("breite_mm", sa.Float(), nullable=True))
    op.add_column("formularfelder", sa.Column("hoehe_mm", sa.Float(), nullable=True))

    # --- Backfill: Seitenumbruch-Replay je Formular ------------------------
    formulare = bind.execute(sa.text("SELECT id, zeilenhoehe_mm FROM formulare")).fetchall()
    for formular_id, zeilenhoehe_mm in formulare:
        felder = bind.execute(
            sa.text(
                """
                SELECT id, raster_zeile, raster_spalte, raster_breite, raster_hoehe
                FROM formularfelder
                WHERE formular_id = :fid
                ORDER BY raster_zeile, raster_spalte
                """
            ),
            {"fid": formular_id},
        ).fetchall()
        if not felder:
            continue
        felder_dicts = [
            {
                "id": f.id,
                "raster_zeile": f.raster_zeile,
                "raster_spalte": f.raster_spalte,
                "raster_breite": f.raster_breite,
                "raster_hoehe": f.raster_hoehe,
            }
            for f in felder
        ]
        positionen = _replay_seitenumbruch(felder_dicts, zeilenhoehe_mm)
        bind.execute(
            sa.text(
                """
                UPDATE formularfelder
                SET seite = :seite, x_mm = :x_mm, y_mm = :y_mm,
                    breite_mm = :breite_mm, hoehe_mm = :hoehe_mm
                WHERE id = :id
                """
            ),
            positionen,
        )
        max_seite = max(p["seite"] for p in positionen)
        bind.execute(
            sa.text("UPDATE formulare SET anzahl_seiten = :n WHERE id = :fid"),
            {"n": max_seite + 1, "fid": formular_id},
        )

    op.alter_column("formularfelder", "seite", nullable=False, server_default="0")
    op.alter_column("formularfelder", "x_mm", nullable=False, server_default="0")
    op.alter_column("formularfelder", "y_mm", nullable=False, server_default="0")
    op.alter_column(
        "formularfelder", "breite_mm", nullable=False, server_default=str(NUTZBARE_BREITE_MM)
    )
    op.alter_column("formularfelder", "hoehe_mm", nullable=False, server_default="8")

    op.create_check_constraint("seite_valid", "formularfelder", "seite >= 0")
    op.create_check_constraint("x_mm_valid", "formularfelder", "x_mm >= 0")
    op.create_check_constraint("y_mm_valid", "formularfelder", "y_mm >= 0")
    op.create_check_constraint("breite_mm_valid", "formularfelder", "breite_mm > 0")
    op.create_check_constraint("hoehe_mm_valid", "formularfelder", "hoehe_mm > 0")
    op.create_check_constraint(
        "x_mm_passt_auf_seite",
        "formularfelder",
        f"x_mm + breite_mm <= {NUTZBARE_BREITE_MM}",
    )

    # --- altes Raster entfernen ---------------------------------------------
    op.drop_constraint("raster_passt_in_zeile", "formularfelder", type_="check")
    op.drop_constraint("raster_hoehe_valid", "formularfelder", type_="check")
    op.drop_constraint("raster_breite_valid", "formularfelder", type_="check")
    op.drop_constraint("raster_spalte_valid", "formularfelder", type_="check")
    op.drop_column("formularfelder", "raster_zeile")
    op.drop_column("formularfelder", "raster_spalte")
    op.drop_column("formularfelder", "raster_breite")
    op.drop_column("formularfelder", "raster_hoehe")

    op.drop_constraint("zeilenhoehe_valid", "formulare", type_="check")
    op.alter_column("formulare", "zeilenhoehe_mm", new_column_name="snap_mm", nullable=True)
    op.alter_column("formulare", "snap_mm", server_default=None)
    op.create_check_constraint(
        "snap_mm_valid", "formulare", "snap_mm IS NULL OR snap_mm BETWEEN 1 AND 50"
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_constraint("snap_mm_valid", "formulare", type_="check")
    op.alter_column("formulare", "snap_mm", new_column_name="zeilenhoehe_mm", nullable=False, server_default="8")
    op.execute("UPDATE formulare SET zeilenhoehe_mm = 8 WHERE zeilenhoehe_mm IS NULL")
    op.create_check_constraint(
        "zeilenhoehe_valid", "formulare", "zeilenhoehe_mm BETWEEN 4 AND 20"
    )

    op.add_column("formularfelder", sa.Column("raster_zeile", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_spalte", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_breite", sa.SmallInteger(), nullable=True))
    op.add_column("formularfelder", sa.Column("raster_hoehe", sa.SmallInteger(), nullable=True))

    formulare = bind.execute(sa.text("SELECT id, zeilenhoehe_mm FROM formulare")).fetchall()
    for formular_id, zeilenhoehe_mm in formulare:
        felder = bind.execute(
            sa.text(
                """
                SELECT id, seite, x_mm, y_mm, breite_mm, hoehe_mm
                FROM formularfelder
                WHERE formular_id = :fid
                ORDER BY seite, y_mm, x_mm
                """
            ),
            {"fid": formular_id},
        ).fetchall()
        if not felder:
            continue
        felder_dicts = [
            {
                "id": f.id,
                "seite": f.seite,
                "x_mm": f.x_mm,
                "y_mm": f.y_mm,
                "breite_mm": f.breite_mm,
                "hoehe_mm": f.hoehe_mm,
            }
            for f in felder
        ]
        raster = _replay_rueckwaerts(felder_dicts, zeilenhoehe_mm)
        bind.execute(
            sa.text(
                """
                UPDATE formularfelder
                SET raster_zeile = :raster_zeile, raster_spalte = :raster_spalte,
                    raster_breite = :raster_breite, raster_hoehe = :raster_hoehe
                WHERE id = :id
                """
            ),
            raster,
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
    op.create_check_constraint("raster_hoehe_valid", "formularfelder", "raster_hoehe >= 1")
    op.create_check_constraint(
        "raster_passt_in_zeile", "formularfelder", "raster_spalte + raster_breite <= 12"
    )

    op.drop_constraint("x_mm_passt_auf_seite", "formularfelder", type_="check")
    op.drop_constraint("hoehe_mm_valid", "formularfelder", type_="check")
    op.drop_constraint("breite_mm_valid", "formularfelder", type_="check")
    op.drop_constraint("y_mm_valid", "formularfelder", type_="check")
    op.drop_constraint("x_mm_valid", "formularfelder", type_="check")
    op.drop_constraint("seite_valid", "formularfelder", type_="check")
    op.drop_column("formularfelder", "hoehe_mm")
    op.drop_column("formularfelder", "breite_mm")
    op.drop_column("formularfelder", "y_mm")
    op.drop_column("formularfelder", "x_mm")
    op.drop_column("formularfelder", "seite")

    op.drop_constraint("anzahl_seiten_valid", "formulare", type_="check")
    op.drop_column("formulare", "anzahl_seiten")
