"""Formular-Modul v2: neue Feldtypen + Datenquelle.

Erweitert den Feldtyp-Katalog (form_fields.feld_typ) um "datei" (generischer
Upload, Bild/PDF -- Ergaenzung zu "foto", das Kamera-Aufnahme meint),
"email"/"telefon" (Text mit passender Validierung/Tastatur statt
generischem "text"), "betrag" (Geldbetrag statt generischer "zahl") und
"adresse" (strukturiert: strasse/plz/ort, analog zum bestehenden
Adresse-Muster bei Kunde/Standort). Zusaetzlich eine neue Datenquelle
"system.jetzt" fuer automatisch gesetzte Zeitstempel-Felder (datum-Typ).

Rein additiv an den CHECK-Constraints -- bestehende Zeilen/Werte bleiben
gueltig, es werden nur weitere erlaubte Werte hinzugefuegt.

Revision ID: 0080
Revises: 0079
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0080"
down_revision: Union[str, None] = "0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALTE_FELD_TYPEN = (
    "text",
    "textarea",
    "zahl",
    "datum",
    "dropdown",
    "mehrfachauswahl",
    "ja_nein",
    "bewertung",
    "foto",
    "unterschrift",
    "gps",
    "qr_scan",
)
_NEUE_FELD_TYPEN = _ALTE_FELD_TYPEN + ("datei", "email", "telefon", "betrag", "adresse")

_ALTE_DATENQUELLEN = (
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
_NEUE_DATENQUELLEN = _ALTE_DATENQUELLEN + ("system.jetzt",)


def upgrade() -> None:
    # Bare Suffixe (kein "ck_form_fields_"-Praefix) -- op.drop_constraint
    # wendet die naming_convention (siehe app/db/base.py) genau wie
    # create_check_constraint auf den Namen an; ein bereits praefigierter
    # Name wuerde sonst doppelt praefigiert (vgl. Docstring in Migration
    # 0076 zur selben Falle bei create_check_constraint).
    op.drop_constraint("feld_typ_valid", "form_fields", type_="check")
    op.create_check_constraint("feld_typ_valid", "form_fields", f"feld_typ IN {_NEUE_FELD_TYPEN}")

    op.drop_constraint("datenquelle_valid", "form_fields", type_="check")
    op.create_check_constraint(
        "datenquelle_valid", "form_fields", f"datenquelle IS NULL OR datenquelle IN {_NEUE_DATENQUELLEN}"
    )


def downgrade() -> None:
    op.drop_constraint("feld_typ_valid", "form_fields", type_="check")
    op.create_check_constraint("feld_typ_valid", "form_fields", f"feld_typ IN {_ALTE_FELD_TYPEN}")

    op.drop_constraint("datenquelle_valid", "form_fields", type_="check")
    op.create_check_constraint(
        "datenquelle_valid", "form_fields", f"datenquelle IS NULL OR datenquelle IN {_ALTE_DATENQUELLEN}"
    )
