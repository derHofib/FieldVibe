from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pymupdf
import pytest
from pypdf import PdfReader

from app.models.bestellung import Bestellung, BestellungPosition
from app.models.lieferant import Lieferant
from app.services import pdf_service
from tests.test_rechnung_pdf_layout import _kunde, _mandant, _rechnung


def _text(pdf_bytes: bytes) -> tuple[int, str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return len(reader.pages), "\n".join(p.extract_text() for p in reader.pages)


def _mahnung(stufe: int, pauschale: str = "40.00", mandant=None) -> bytes:
    return pdf_service.generate_mahnung_pdf(
        mandant or _mandant(),
        _rechnung(rechnungsnummer="R-00042"),
        _kunde(),
        stufe,
        21,
        Decimal("357.00"),
        Decimal("1.23"),
        Decimal(pauschale),
    )


@pytest.mark.parametrize(
    "stufe,label,satz",
    [
        (1, "1. Mahnung", "sicherlich ist Ihnen entgangen"),
        (2, "2. Mahnung", "keinen Zahlungseingang"),
        (3, "3. Mahnung", "letztmalig"),
    ],
)
def test_mahnung_stufen(stufe, label, satz):
    seiten, text = _text(_mahnung(stufe))
    flach = " ".join(text.split())
    assert seiten == 1
    assert label in text
    assert "Gesamt fällig" in text
    assert "€" in text and "EUR" not in text
    assert "Seite 1 von 1" in text
    assert "Sehr geehrte Damen und Herren," in text
    assert satz in flach
    assert "seit 21 Tagen" in flach
    assert "zu Rechnung R-00042 vom 11.08.2026" in flach
    assert "Fällig seit" in text and "10.09.2026" in text
    assert "398,23 €" in text  # 357 + 1,23 + 40


def test_mahnung_mit_und_ohne_pauschale():
    _, mit = _text(_mahnung(2, "40.00"))
    _, ohne = _text(_mahnung(2, "0"))
    assert "Mahnpauschale (§ 288 Abs. 5 BGB)" in mit
    assert "Mahnpauschale" not in ohne
    assert "358,23 €" in ohne


def test_mahnung_zahlungshinweis_nur_mit_iban():
    _, mit = _text(_mahnung(1))
    _, ohne = _text(_mahnung(1, mandant=_mandant(iban=None)))
    assert "unter Angabe der Rechnungsnummer R-00042" in " ".join(mit.split())
    assert "unter Angabe der Rechnungsnummer" not in " ".join(ohne.split())
    assert "gegenstandslos" in ohne
    assert "Mit freundlichen Grüßen" in ohne


def test_mahnung_defektes_logo_bricht_nicht_ab():
    pdf = pdf_service.generate_mahnung_pdf(
        _mandant(), _rechnung(), _kunde(), 1, 5, Decimal("10"), Decimal("0"), Decimal("0"), logo_bytes=b"kein bild"
    )
    assert PdfReader(BytesIO(pdf)).pages


def _lieferant() -> Lieferant:
    return Lieferant(id=uuid4(), name="Großhandel Schmidt", email="bestellung@schmidt.example", telefon="0111 2222")


def _bestellung(**kw) -> Bestellung:
    d = {
        "id": uuid4(),
        "bestellnummer": "B-00005",
        "status": "entwurf",
        "erstellt_von": uuid4(),
        "created_at": datetime(2026, 9, 2, tzinfo=timezone.utc),
    }
    d.update(kw)
    return Bestellung(**d)


def _bpositionen(anzahl: int) -> list[BestellungPosition]:
    return [
        BestellungPosition(
            position=i,
            material_id=uuid4(),
            beschreibung=f"Artikel {i} – Kupferrohr äöüß" if i != 3 else "Sehr lange Beschreibung " * 12,
            menge=Decimal("4"),
            einheit="Stk",
            einzelpreis=Decimal("12.50"),
        )
        for i in range(1, anzahl + 1)
    ]


def test_bestellung_mehrseitig():
    pdf = pdf_service.generate_bestellung_pdf(
        _mandant(), _bestellung(notiz="Bitte Anlieferung vormittags."), _bpositionen(40), _lieferant()
    )
    seiten, text = _text(pdf)
    reader = PdfReader(BytesIO(pdf))
    assert seiten > 1
    assert "Hiermit bestellen wir folgende Artikel:" in text
    assert "Bestellsumme" in text
    assert "€" in text and "EUR" not in text
    assert "Großhandel Schmidt" in text and "bestellung@schmidt.example" in text
    assert "Bestellung B-00005 · Seite 2" in reader.pages[1].extract_text().replace("\n", " ")
    assert f"Seite {seiten} von {seiten}" in text
    assert "Bitte Anlieferung vormittags." in text
    assert "Bitte bestätigen Sie uns die Bestellung und den Liefertermin." in " ".join(text.split())
    assert "Art.-Nr." not in text  # BestellungPosition kennt keine Artikelnummer
    assert "überweisen" not in text
    assert "Artikel" in reader.pages[-1].extract_text()


def test_bestellung_ohne_lieferant_und_positionen():
    seiten, text = _text(pdf_service.generate_bestellung_pdf(_mandant(), _bestellung(), [], None))
    assert seiten == 1 and "Bestellung" in text


def test_info_wert_umbruch_ueberschreitet_breite_nie():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_font("Helvetica", "", 9)
    for wert in (
        "erika.beispiel@elektro-mueller.example",
        "x" * 80,
        "sehr.lange.email.adresse.ohne.at.zeichen@an-einer-ziemlich-langen-domain-example.com",
        "kurz",
    ):
        zeilen = pdf_service._info_wert_zeilen(pdf, wert, 38)
        assert all(pdf.get_string_width(z) <= 38 for z in zeilen)
        assert "".join(zeilen) == wert
    assert pdf_service._info_wert_zeilen(pdf, "erika.beispiel@elektro-mueller.example", 38)== ["erika.beispiel@elektro-", "mueller.example"]


def test_lange_email_im_info_block_bleibt_im_rand():
    from app.models.angebot import Angebot
    from app.models.user import User
    from datetime import date

    angebot = Angebot(
        id=uuid4(), kunde_id=uuid4(), angebotsnummer="A-00001", status="entwurf", mwst_satz=Decimal("19"),
        gueltig_bis=date(2026, 10, 31), erstellt_von=uuid4(), created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    bearbeiter = User(id=uuid4(), name="Erika Beispiel", email="erika.beispiel@elektro-mueller.example")
    pdf = pdf_service.generate_angebot_pdf(_mandant(), angebot, [], _kunde(), bearbeiter)
    seite = pymupdf.open(stream=pdf)[0]
    rand = 190 / 25.4 * 72
    for x0, y0, x1, y1, wort, *_ in seite.get_text("words"):
        assert x1 <= rand + 0.5, wort
    text = seite.get_text()
    assert "erika.beispiel@" in text and "mueller.example" in text
    # Titel liegt unterhalb des (umgebrochenen) Info-Blocks
    titel_y = min(w[1] for w in seite.get_text("words") if w[4] == "Angebot")
    email_y = max(w[3] for w in seite.get_text("words") if w[4] == "mueller.example" and w[0] > 300)
    assert titel_y > email_y
