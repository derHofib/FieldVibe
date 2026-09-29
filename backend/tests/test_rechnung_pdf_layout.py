from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import pdf_service

_V1, _V2 = uuid4(), uuid4()


def _mandant(**fd) -> Mandant:
    firmendaten = {
        "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
        "steuernummer": "12/345/67890",
        "ust_idnr": "DE123456789",
        "iban": "DE89 3704 0044 0532 0130 00",
        "bic": "COBADEFFXXX",
        "bank_name": "Commerzbank",
        "telefon": "0123 456789",
        "email": "info@mueller.example",
    }
    firmendaten.update(fd)
    return Mandant(id=uuid4(), name="Elektro Müller GmbH", slug="mueller", firmendaten=firmendaten)


def _kunde() -> Kunde:
    return Kunde(
        id=uuid4(),
        kundennummer="K-1",
        name="Café Sonnenschein",
        typ="gewerbe",
        ansprechpartner=[],
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
        portal_slug=uuid4().hex,
    )


def _rechnung(**kw) -> Rechnung:
    d = {
        "id": uuid4(),
        "kunde_id": uuid4(),
        "rechnungsnummer": "R-00001",
        "leistungsdatum": date(2026, 8, 10),
        "faellig_am": date(2026, 9, 10),
        "betrag_netto": Decimal("300.00"),
        "mwst_satz": Decimal("19.00"),
        "status": "entwurf",
        "erstellt_von": uuid4(),
        "ist_storno": False,
        "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
    }
    d.update(kw)
    return Rechnung(**d)


def _positionen(anzahl: int = 40) -> list[RechnungPosition]:
    lang = "Sehr lange Beschreibung – Prüfung und Wartung der Anlage " * 12
    ergebnis = []
    for i in range(1, anzahl + 1):
        ergebnis.append(
            RechnungPosition(
                position=i,
                beschreibung=lang if i == 7 else f"Leistung {i} – Kabelverlegung äöüß",
                menge=Decimal("3.5") if i % 2 else Decimal("2"),
                einheit="Std",
                einzelpreis=Decimal("45.50"),
                vorgang_id=None if i <= 10 else (_V1 if i <= 25 else _V2),
            )
        )
    return ergebnis


def _text(pdf_bytes: bytes) -> tuple[int, str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    return len(reader.pages), "\n".join(p.extract_text() for p in reader.pages)


def _koepfe():
    return {_V1: ("V-00051", "Heizung Süd"), _V2: ("V-00052", "Zählerschrank")}


def test_rechnung_viele_positionen_mehrseitig():
    pdf = pdf_service.generate_rechnung_pdf(
        _mandant(), _rechnung(), _kunde(), _positionen(), vorgang_koepfe=_koepfe()
    )
    seiten, text = _text(pdf)
    assert seiten > 1
    assert "Rechnungsbetrag" in text
    assert "Zwischensumme" in text
    assert "Seite 1 von" in text
    assert f"Seite {seiten} von {seiten}" in text
    assert "V-00051" in text and "V-00052" in text
    assert "€" in text
    assert "EUR" not in text
    assert "Bitte überweisen Sie" in text


def test_rechnung_kleinunternehmer():
    pdf = pdf_service.generate_rechnung_pdf(
        _mandant(ist_kleinunternehmer=True), _rechnung(), _kunde(), _positionen(5), vorgang_koepfe=_koepfe()
    )
    _, text = _text(pdf)
    assert "Rechnungsbetrag" in text
    assert "§ 19 UStG" in text
    assert "USt." not in text.replace("USt-IdNr", "")


def test_rechnung_storno():
    orig = _rechnung(rechnungsnummer="R-00000")
    pdf = pdf_service.generate_rechnung_pdf(
        _mandant(),
        _rechnung(ist_storno=True, rechnungsnummer="R-00002"),
        _kunde(),
        _positionen(4),
        storniert_rechnung=orig,
    )
    _, text = _text(pdf)
    assert "Stornorechnung" in text
    assert "Storniert Rechnung R-00000" in text
    assert "Bitte überweisen" not in text


def test_rechnung_ohne_positionen_zeigt_nur_summenblock():
    pdf = pdf_service.generate_rechnung_pdf(_mandant(), _rechnung(), _kunde(), [])
    _, text = _text(pdf)
    assert "Rechnungsbetrag" in text
    assert "357,00 €" in text
    assert "BESCHREIBUNG" not in text


def test_rechnung_ohne_iban_ohne_zahlungshinweis():
    pdf = pdf_service.generate_rechnung_pdf(_mandant(iban=None), _rechnung(), _kunde(), _positionen(3))
    _, text = _text(pdf)
    assert "Bitte überweisen" not in text


def test_rechnung_mit_defektem_logo_faellt_zurueck():
    pdf = pdf_service.generate_rechnung_pdf(
        _mandant(), _rechnung(), _kunde(), _positionen(3), logo_bytes=b"kein bild"
    )
    assert pdf.startswith(b"%PDF")


def _letzte_seite(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return reader.pages[-1].extract_text()


def test_rechnung_summenblock_steht_nie_allein_auf_der_letzten_seite():
    # Durchlauf ueber viele Positionsanzahlen, damit mindestens ein Fall genau
    # an der Seitengrenze liegt, an dem der Summenblock nicht mehr passt.
    seiten_je_anzahl = {}
    for anzahl in range(8, 40):
        pdf = pdf_service.generate_rechnung_pdf(_mandant(), _rechnung(), _kunde(), _positionen(anzahl)[:anzahl])
        seiten, _ = _text(pdf)
        seiten_je_anzahl[anzahl] = seiten
        letzte = _letzte_seite(pdf)
        assert "Rechnungsbetrag" in letzte
        if seiten > 1:
            assert "Leistung" in letzte, f"Summenblock allein auf Seite {seiten} bei {anzahl} Positionen"
    assert len(set(seiten_je_anzahl.values())) > 1


def test_rechnung_letzte_position_mit_zwischensumme_wandert_mit():
    for anzahl in range(12, 40):
        pdf = pdf_service.generate_rechnung_pdf(
            _mandant(), _rechnung(), _kunde(), _positionen(anzahl), vorgang_koepfe=_koepfe()
        )
        seiten, _ = _text(pdf)
        letzte = _letzte_seite(pdf)
        assert "Rechnungsbetrag" in letzte
        if seiten > 1:
            assert "Leistung" in letzte
            # Zwischensumme der letzten Gruppe steht auf derselben Seite wie
            # die letzte Position.
            assert "Zwischensumme" in letzte


def test_rechnung_titel_beginnt_frueh_bei_kurzem_adressblock():
    kunde = _kunde()
    pdf = pdf_service.generate_rechnung_pdf(_mandant(), _rechnung(), kunde, _positionen(2))
    reader = PdfReader(BytesIO(pdf))
    ys = []

    def visitor(text, cm, tm, font_dict, font_size):
        if text.strip() == "Rechnung" and font_size >= 19:
            ys.append(tm[5])

    reader.pages[0].extract_text(visitor_text=visitor)
    assert ys
    # PDF-y ist von unten gezaehlt (A4 = 297 mm = 841.9 pt) und die Grundlinie
    # liegt ~6,5 mm unter der Zellenoberkante: Zelle bei ~92,5 mm (Ende Info-
    # Block + 10 mm) statt der frueheren fixen 100 mm (Grundlinie ~106,5).
    y_mm = (841.89 - ys[0]) * 25.4 / 72
    assert 96 <= y_mm <= 102
