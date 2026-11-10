from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader

from app.models.angebot import Angebot, AngebotPosition
from app.models.user import User
from app.services import pdf_service
from tests.test_rechnung_pdf_layout import _kunde, _mandant


def _angebot(**kw) -> Angebot:
    d = {
        "id": uuid4(),
        "kunde_id": uuid4(),
        "angebotsnummer": "A-00007",
        "status": "entwurf",
        "mwst_satz": Decimal("19.00"),
        "gueltig_bis": date(2026, 10, 31),
        "erstellt_von": uuid4(),
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    }
    d.update(kw)
    return Angebot(**d)


def _positionen(anzahl: int, mit_artikelnummer: bool = True) -> list[AngebotPosition]:
    ergebnis = []
    for i in range(1, anzahl + 1):
        ergebnis.append(
            AngebotPosition(
                position=i,
                artikelnummer=f"ART-{1000 + i}" if mit_artikelnummer and i % 2 else None,
                beschreibung=(
                    "Sehr lange Beschreibung – Montage und Inbetriebnahme inklusive Einweisung " * 5
                    if i == 3
                    else f"Leistung {i} – Kabelverlegung äöüß"
                ),
                menge=Decimal("2"),
                einheit="Stk",
                einzelpreis=Decimal("45.50"),
            )
        )
    return ergebnis


def _bearbeiter() -> User:
    return User(id=uuid4(), name="Erika Beispiel", email="erika@mueller.example")


def _text(pdf_bytes: bytes) -> tuple[int, str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return len(reader.pages), "\n".join(p.extract_text() for p in reader.pages)


def test_angebot_mehrseitig_mit_artikelnummer():
    pdf = pdf_service.generate_angebot_pdf(
        _mandant(), _angebot(), _positionen(40), _kunde(), _bearbeiter()
    )
    seiten, text = _text(pdf)
    reader = PdfReader(BytesIO(pdf))
    assert seiten > 1
    assert "Angebotssumme" in text
    assert "Seite 1 von" in text
    assert f"Seite {seiten} von {seiten}" in text
    assert "Art.-Nr. ART-1001" in text
    assert "Angebot A-00007 · Seite 2" in reader.pages[1].extract_text().replace("\n", " ")
    assert "Vielen Dank für Ihre Anfrage" in text
    assert "Erika Beispiel" in text and "erika@mueller.example" in text
    assert "Dieses Angebot ist gültig bis 31.10.2026." in text
    assert "Wir freuen uns auf Ihren Auftrag." in text
    assert "Mit freundlichen Grüßen" in text
    assert "€" in text and "EUR" not in text
    # Summenblock nie allein auf der letzten Seite
    assert "Leistung" in reader.pages[-1].extract_text()


def test_angebot_summenblock_steht_nie_allein():
    for anzahl in range(8, 40):
        pdf = pdf_service.generate_angebot_pdf(_mandant(), _angebot(), _positionen(anzahl), _kunde())
        reader = PdfReader(BytesIO(pdf))
        letzte = reader.pages[-1].extract_text()
        assert "Angebotssumme" in letzte
        assert "Leistung" in letzte or len(reader.pages) == 1


def test_angebot_ohne_artikelnummer_und_ohne_gueltigkeit():
    pdf = pdf_service.generate_angebot_pdf(
        _mandant(), _angebot(gueltig_bis=None), _positionen(4, mit_artikelnummer=False), _kunde()
    )
    _, text = _text(pdf)
    assert "Art.-Nr." not in text
    assert "Gültig bis" not in text
    assert "Dieses Angebot ist gültig" not in text
    assert "Ansprechpartner" not in text
    assert "Angebotssumme" in text


def test_angebot_kleinunternehmer():
    pdf = pdf_service.generate_angebot_pdf(
        _mandant(ist_kleinunternehmer=True), _angebot(), _positionen(3), _kunde()
    )
    _, text = _text(pdf)
    assert "Angebotssumme" in text
    assert "§ 19 UStG" in text
    assert "zzgl." not in text


def test_angebot_ohne_positionen_und_defektes_logo():
    pdf = pdf_service.generate_angebot_pdf(_mandant(), _angebot(), [], _kunde(), logo_bytes=b"kein bild")
    _, text = _text(pdf)
    assert "Angebotssumme" in text
