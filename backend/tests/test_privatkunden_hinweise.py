"""Hinweise fuer Privatkunden (§ 14 Abs. 4 Nr. 9 UStG, § 35a EStG) auf PDF und in der E-Rechnung:
Aufbewahrungshinweis, Ausweis der Arbeitskosten, Schalter, Verhalten je Rechnungsart."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pymupdf
import pytest
from lxml import etree

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import pdf_service, privatkunden_service
from tests.conftest import auth_headers, login

AUFBEWAHRUNG = "Als Privatperson sind Sie verpflichtet, diese Rechnung zwei Jahre lang aufzubewahren"
ARBEITSKOSTEN = "Davon Arbeitskosten inkl. Fahrt- und Maschinenkosten (§ 35a EStG)"
UNBAR = "Die Steuerermäßigung setzt voraus, dass die Rechnung unbar bezahlt wird"


def _mandant(**fd) -> Mandant:
    firmendaten = {
        "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
        "steuernummer": "12/345/67890",
        "ust_idnr": "DE123456789",
        "iban": "DE89 3704 0044 0532 0130 00",
        "bic": "COBADEFFXXX",
        "telefon": "0123 456789",
        "email": "info@mueller.example",
    }
    firmendaten.update(fd)
    return Mandant(id=uuid4(), name="Elektro Müller GmbH", slug="mueller", firmendaten=firmendaten)


def _kunde(**kw) -> Kunde:
    daten = {
        "id": uuid4(),
        "kundennummer": "K-1",
        "name": "Erika Beispiel",
        "typ": "privat",
        "ansprechpartner": [],
        "adresse": {"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        "portal_slug": uuid4().hex,
    }
    daten.update(kw)
    return Kunde(**daten)


def _rechnung(**kw) -> Rechnung:
    daten = {
        "id": uuid4(),
        "kunde_id": uuid4(),
        "rechnungsnummer": "R-00001",
        "leistungsdatum": date(2026, 8, 10),
        "betrag_netto": Decimal("0.00"),
        "mwst_satz": Decimal("19.00"),
        "status": "entwurf",
        "erstellt_von": uuid4(),
        "ist_storno": False,
        "rechnungsart": "rechnung",
        "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
    }
    daten.update(kw)
    return Rechnung(**daten)


def _pos(nr, beschreibung, menge, preis, quelle, satz="19.00", **kw) -> RechnungPosition:
    return RechnungPosition(
        position=nr,
        beschreibung=beschreibung,
        menge=Decimal(menge),
        einheit="Std",
        einzelpreis=Decimal(preis),
        quelle=quelle,
        steuer_kategorie="S",
        steuer_satz=Decimal(satz),
        **kw,
    )


# Arbeit 137,50 + Fahrt 7,56 = 145,06 netto (19 %: 27,56 USt), Material 23,45 netto (7 %).
def _handwerker_positionen() -> list[RechnungPosition]:
    return [
        _pos(1, "Arbeitszeit", "2.5", "55", "zeit"),
        _pos(2, "Anfahrt", "18", "0.42", "fahrtkosten"),
        _pos(3, "Kabel", "1", "23.45", "material", satz="7.00"),
    ]


def _text(pdf: bytes) -> str:
    dok = pymupdf.open(stream=pdf, filetype="pdf")
    return " ".join(" ".join(seite.get_text() for seite in dok).split())


def _pdf(mandant=None, rechnung=None, kunde=None, positionen=None, **kw) -> str:
    return _text(
        pdf_service.generate_rechnung_pdf(
            mandant or _mandant(),
            rechnung or _rechnung(),
            kunde or _kunde(),
            _handwerker_positionen() if positionen is None else positionen,
            **kw,
        )
    )


def test_privatkunde_bekommt_aufbewahrungshinweis_und_arbeitskosten():
    text = _pdf()
    assert "Hinweis nach § 14 Abs. 4 Nr. 9 UStG" in text
    assert AUFBEWAHRUNG in text
    assert "§ 14b Abs. 1 Satz 5 UStG" in text
    assert f"{ARBEITSKOSTEN}: Netto 145,06 €, Umsatzsteuer 27,56 €, Brutto 172,62 €" in text
    assert UNBAR in text  # IBAN vorhanden


def test_unbare_zahlung_nur_mit_zahlungsangaben():
    text = _pdf(mandant=_mandant(iban=None))
    assert ARBEITSKOSTEN in text and AUFBEWAHRUNG in text
    assert UNBAR not in text


@pytest.mark.parametrize(
    "kunde",
    [
        _kunde(typ="gewerbe"),
        _kunde(typ="oeffentlich"),
        _kunde(typ="hausverwaltung"),
        _kunde(typ=None, ust_idnr="DE987654321"),
        _kunde(typ="privat", leitweg_id="991-12345-73"),
    ],
)
def test_gewerbliche_kunden_bekommen_keine_hinweise(kunde):
    text = _pdf(kunde=kunde)
    assert AUFBEWAHRUNG not in text and ARBEITSKOSTEN not in text and "§ 35a" not in text


def test_kunde_ohne_typ_gilt_als_privatkunde():
    assert AUFBEWAHRUNG in _pdf(kunde=_kunde(typ=None))


def test_schalter_aus_unterdrueckt_alle_hinweise():
    text = _pdf(mandant=_mandant(privatkunden_hinweise=False))
    assert AUFBEWAHRUNG not in text and ARBEITSKOSTEN not in text and UNBAR not in text
    # nicht gesetzt = an
    assert AUFBEWAHRUNG in _pdf(mandant=_mandant())
    assert AUFBEWAHRUNG in _pdf(mandant=_mandant(privatkunden_hinweise=True))


@pytest.mark.parametrize(
    "positionen",
    [
        # Leistungsverzeichnis-Positionen koennen Lohn und Material mischen
        [_pos(1, "Arbeitszeit", "2", "55", "zeit"), _pos(2, "LV-Position", "1", "100", "leistung")],
        # manuelle Positionen ohne Quelle: keine verlaessliche Zuordnung
        [_pos(1, "Arbeitszeit", "2", "55", "zeit"), _pos(2, "Sonstiges", "1", "10", None)],
        # nur Material: keine Arbeitskosten
        [_pos(1, "Kabel", "5", "3", "material")],
        [],
    ],
)
def test_ohne_verlaessliche_zuordnung_nur_aufbewahrungshinweis(positionen):
    text = _pdf(positionen=positionen, rechnung=_rechnung(betrag_netto=Decimal("100.00")))
    assert AUFBEWAHRUNG in text
    assert ARBEITSKOSTEN not in text and UNBAR not in text


def test_nur_arbeit_zeigt_die_gesamte_summe_als_arbeitskosten():
    text = _pdf(positionen=[_pos(1, "Arbeitszeit", "2", "50", "zeit"), _pos(2, "Anfahrt", "1", "20", "fahrzeit")])
    assert f"{ARBEITSKOSTEN}: Netto 120,00 €, Umsatzsteuer 22,80 €, Brutto 142,80 €" in text


def test_arbeitskosten_rechnen_je_steuersatz():
    positionen = [
        _pos(1, "Arbeit 19", "1", "100", "zeit"),
        _pos(2, "Arbeit 7", "1", "100", "zeit", satz="7.00"),
        _pos(3, "Material", "1", "50", "material"),
    ]
    text = _pdf(positionen=positionen)
    assert f"{ARBEITSKOSTEN}: Netto 200,00 €, Umsatzsteuer 26,00 €, Brutto 226,00 €" in text


def test_kleinunternehmer_ohne_umsatzsteuer_im_arbeitskostenausweis():
    positionen = [_pos(1, "Arbeitszeit", "2", "50", "zeit", satz="0.00"), _pos(2, "Kabel", "1", "10", "material", satz="0.00")]
    for p in positionen:
        p.steuer_kategorie = "E"
    text = _pdf(mandant=_mandant(ist_kleinunternehmer=True), positionen=positionen)
    assert f"{ARBEITSKOSTEN}: 100,00 € (ohne Umsatzsteuer, § 19 UStG)" in text
    assert AUFBEWAHRUNG in text


def test_abschlag_und_schluss_nur_aufbewahrungshinweis():
    for art in ("abschlag", "schluss"):
        text = _pdf(rechnung=_rechnung(rechnungsart=art))
        assert AUFBEWAHRUNG in text, art
        assert ARBEITSKOSTEN not in text and UNBAR not in text, art


def test_gutschrift_und_storno_ohne_hinweise():
    gutschrift = _pdf(
        rechnung=_rechnung(rechnungsart="gutschrift", gutschrift_grund="Fehlbestellung"),
        positionen=[_pos(1, "Arbeitszeit", "-1", "55", "zeit")],
        bezug_rechnung=_rechnung(rechnungsnummer="R-0"),
    )
    assert "Gutschrift" in gutschrift
    storno = _pdf(rechnung=_rechnung(ist_storno=True), storniert_rechnung=_rechnung(rechnungsnummer="R-0"))
    assert "Stornorechnung" in storno
    for text in (gutschrift, storno):
        assert AUFBEWAHRUNG not in text and ARBEITSKOSTEN not in text and "§ 35a" not in text


def test_hinweise_bei_vielen_positionen_auf_letzter_seite():
    positionen = [_pos(i, f"Arbeitszeit {i}", "1", "10", "zeit") for i in range(1, 60)]
    pdf = pdf_service.generate_rechnung_pdf(_mandant(), _rechnung(), _kunde(), positionen)
    dok = pymupdf.open(stream=pdf, filetype="pdf")
    assert dok.page_count > 1
    letzte = " ".join(dok[dok.page_count - 1].get_text().split())
    assert AUFBEWAHRUNG in letzte and ARBEITSKOSTEN in letzte and "Mit freundlichen Grüßen" in letzte


def test_hinweise_fuer_liefert_texte_in_reihenfolge():
    hinweise = privatkunden_service.hinweise_fuer(_mandant(), _rechnung(), _kunde(), _handwerker_positionen())
    texte = hinweise.texte()
    assert [t.startswith(p) for t, p in zip(texte, ("Davon", "Hinweis zu § 35a", "Hinweis nach § 14"))] == [True] * 3
    assert privatkunden_service.hinweise_fuer(_mandant(), _rechnung(), _kunde(typ="gewerbe"), []) is None


# --- Versand: PDF archiviert, E-Rechnung-Vermerk -------------------------------------------------

_FIRMA_API = {
    "e_rechnung_modus": "alle",
    "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
    "ust_idnr": "DE123456789",
    "iban": "DE89 3704 0044 0532 0130 00",
}
_PRIVAT = {"typ": "privat", "adresse": {"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"}}


async def _versendet(client, make_mandant, make_user, make_kunde, firmendaten, kunde_kw, positionen=None):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, **kunde_kw)
    token = await login(client, admin.email, "pw-123456")
    h = auth_headers(token)
    assert (
        await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": firmendaten})
    ).status_code == 200
    angelegt = await client.post(
        "/api/rechnungen",
        headers=h,
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            "positionen": positionen
            or [
                {"beschreibung": "Arbeitszeit", "menge": "2", "einzelpreis": "50", "quelle": "zeit"},
                {"beschreibung": "Kabel", "menge": "1", "einzelpreis": "10", "quelle": "material"},
            ],
        },
    )
    assert angelegt.status_code == 201, angelegt.text
    versendet = await client.patch(f"/api/rechnungen/{angelegt.json()['id']}", headers=h, json={"status": "versendet"})
    assert versendet.status_code == 200, versendet.text
    return h, versendet.json()


@pytest.mark.asyncio
async def test_archiviertes_pdf_traegt_die_hinweise(client, make_mandant, make_user, make_kunde):
    h, rechnung = await _versendet(client, make_mandant, make_user, make_kunde, {"iban": "DE89 3704 0044 0532 0130 00"}, _PRIVAT)
    pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=h)
    text = _text(pdf.content)
    assert AUFBEWAHRUNG in text
    assert f"{ARBEITSKOSTEN}: Netto 100,00 €, Umsatzsteuer 19,00 €, Brutto 119,00 €" in text
    # E-Rechnung aus: normales PDF ohne XML
    assert rechnung["xml_object_key"] is None


@pytest.mark.asyncio
async def test_e_rechnung_vermerk_entspricht_dem_pdf_text(client, make_mandant, make_user, make_kunde):
    h, rechnung = await _versendet(client, make_mandant, make_user, make_kunde, _FIRMA_API, _PRIVAT)
    xml = (await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=h)).content
    ns = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
    vermerke = [e.text for e in etree.fromstring(xml).xpath("//ram:IncludedNote/ram:Content", namespaces=ns)]
    pdf_text = _text((await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=h)).content)
    assert len(vermerke) == 3
    for vermerk in vermerke:
        assert " ".join(vermerk.split()) in pdf_text
    assert any(v.startswith(ARBEITSKOSTEN) for v in vermerke) and any(AUFBEWAHRUNG in v for v in vermerke)


@pytest.mark.asyncio
async def test_schalter_aus_auch_im_versendeten_beleg(client, make_mandant, make_user, make_kunde):
    h, rechnung = await _versendet(
        client, make_mandant, make_user, make_kunde, {**_FIRMA_API, "privatkunden_hinweise": False}, _PRIVAT
    )
    xml = (await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=h)).content.decode()
    pdf_text = _text((await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=h)).content)
    assert "aufzubewahren" not in xml and AUFBEWAHRUNG not in pdf_text


@pytest.mark.asyncio
async def test_gewerblicher_kunde_ohne_vermerke_in_der_xml(client, make_mandant, make_user, make_kunde):
    kunde_kw = {"typ": "gewerbe", "ust_idnr": "DE987654321", "adresse": _PRIVAT["adresse"]}
    h, rechnung = await _versendet(client, make_mandant, make_user, make_kunde, _FIRMA_API, kunde_kw)
    xml = (await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=h)).content
    assert b"IncludedNote" not in xml


@pytest.mark.asyncio
async def test_kundenportal_pdf_traegt_die_hinweise(client, make_mandant, make_user, make_kunde):
    # Das Portal erzeugt das PDF ueber dieselbe Funktion; die Hinweise duerfen nicht fehlen.
    from tests.test_kundenportal import _kunden_login, _make_zugang

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, **_PRIVAT)
    token = await login(client, admin.email, "pw-123456")
    h = auth_headers(token)
    angelegt = await client.post(
        "/api/rechnungen",
        headers=h,
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            "positionen": [{"beschreibung": "Arbeitszeit", "einzelpreis": "50", "quelle": "zeit"}],
        },
    )
    assert angelegt.status_code == 201, angelegt.text
    versendet = await client.patch(f"/api/rechnungen/{angelegt.json()['id']}", headers=h, json={"status": "versendet"})
    assert versendet.status_code == 200
    zugang = await _make_zugang(mandant, kunde)
    tokens = await _kunden_login(client, zugang.email, "kunden-pw-123")
    pdf = await client.get(
        f"/api/kundenportal/rechnungen/{angelegt.json()['id']}/pdf", headers=auth_headers(tokens["access_token"])
    )
    assert pdf.status_code == 200
    assert AUFBEWAHRUNG in _text(pdf.content)
