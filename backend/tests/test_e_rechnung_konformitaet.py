"""Konformitaet der ausgehenden E-Rechnung (CII, Profil EN 16931) gegen die CEN-
Geschaeftsregeln (Schematron, kompiliert als XSLT) -- ueber die echte Pipeline
(API -> rechnung_service -> e_invoice_service), nicht ueber handgeschriebene XML.

Braucht das Pruefwerkzeug aus scripts/e-rechnung/installieren.sh (Java + Cache
unter .cache/e-rechnung bzw. EN16931_CACHE_DIR); ohne wird uebersprungen, damit die
normale Backend-CI nicht davon abhaengt. Geprueft wird NUR EN 16931 -- nicht das
XRechnung-Profil, nicht Peppol (siehe docs/konzepte/E_RECHNUNG_PRUEFUNG.md)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import auth_headers
from tests.test_steuer_freischaltung import (
    _E_RECHNUNG,
    _KUNDE_E_RECHNUNG,
    _POS_AE,
    _POS_E,
    _POS_S,
    _POS_Z,
    _rechnung,
    _versenden,
)
from tests.test_steuer_je_position import _admin

_REPO = Path(__file__).resolve().parents[2]
_SKRIPT = _REPO / "scripts" / "e-rechnung" / "pruefen.sh"
_CACHE = Path(os.environ.get("EN16931_CACHE_DIR") or _REPO / ".cache" / "e-rechnung")


@pytest.fixture(autouse=True)
def _werkzeug_vorhanden():
    if shutil.which("java") is None or not (_CACHE / "installiert.txt").is_file():
        pytest.skip("Prüfwerkzeug nicht installiert (scripts/e-rechnung/installieren.sh ausführen, Java nötig)")


def _pruefe_en16931(xml: bytes, tmp_path: Path, name: str) -> None:
    datei = tmp_path / f"{name}.xml"
    datei.write_bytes(xml)
    if os.environ.get("E_RECHNUNG_XML_DIR"):  # erzeugte XML zur Fehlersuche ablegen
        Path(os.environ["E_RECHNUNG_XML_DIR"], datei.name).write_bytes(xml)
    ergebnis = subprocess.run(
        ["bash", str(_SKRIPT), str(datei)], capture_output=True, text=True, timeout=180, env={**os.environ}
    )
    print(ergebnis.stdout)  # Warnungen der Regeln sichtbar machen (pytest -s)
    assert ergebnis.returncode == 0, f"EN-16931-Regelverstoesse in '{name}':\n{ergebnis.stdout}{ergebnis.stderr}"


async def _versendet_xml(client, token, kunde, positionen, **extra) -> bytes:
    rechnung = await _rechnung(client, token, kunde, positionen, **extra)
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 200, versand.text
    assert versand.json()["xml_object_key"] is not None
    antwort = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))
    assert antwort.status_code == 200
    return antwort.content


async def _admin_e_rechnung(client, make_mandant, make_user, make_kunde, firmendaten=None, **kunde_kw):
    return await _admin(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten=firmendaten or _E_RECHNUNG,
        **{**_KUNDE_E_RECHNUNG, **kunde_kw},
    )


@pytest.mark.asyncio
async def test_pruefwerkzeug_schlaegt_bei_regelverstoss_an(client, make_mandant, make_user, make_kunde, tmp_path):
    # Negativkontrolle: ein Z-Block mit Befreiungsgrund verletzt BR-Z-10 -- sonst
    # wuerde ein kaputtes Werkzeug alle Tests still gruen faerben.
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_Z])
    kaputt = xml.replace(b"<ram:BasisAmount>", b"<ram:ExemptionReason>x</ram:ExemptionReason><ram:BasisAmount>", 1)
    assert kaputt != xml
    datei = tmp_path / "kaputt.xml"
    datei.write_bytes(kaputt)
    ergebnis = subprocess.run(["bash", str(_SKRIPT), str(datei)], capture_output=True, text=True, timeout=180)
    assert ergebnis.returncode == 1
    assert "[BR-Z-10]" in ergebnis.stdout


@pytest.mark.asyncio
async def test_einzelsatz_19(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_S])
    _pruefe_en16931(xml, tmp_path, "einzelsatz_19")


@pytest.mark.asyncio
async def test_mischsatz_19_und_7(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    positionen = [
        {"beschreibung": "Material 19", "menge": "1", "einzelpreis": "10.10"},
        {"beschreibung": "Material 7", "menge": "1", "einzelpreis": "3.50", "steuer_satz": "7"},
        {"beschreibung": "Material 7 b", "menge": "3", "einzelpreis": "19.99", "steuer_satz": "7"},
    ]
    xml = await _versendet_xml(client, token, kunde, positionen)
    _pruefe_en16931(xml, tmp_path, "mischsatz_19_7")


@pytest.mark.asyncio
async def test_z_pv_12_abs_3(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_Z])
    _pruefe_en16931(xml, tmp_path, "z_pv")


@pytest.mark.asyncio
async def test_e_sonstige_befreiung(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_E])
    _pruefe_en16931(xml, tmp_path, "e_befreiung")


@pytest.mark.asyncio
async def test_ae_13b_mit_ust_idnrn(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_AE])
    _pruefe_en16931(xml, tmp_path, "ae_13b")


@pytest.mark.asyncio
async def test_alle_kategorien_in_einem_beleg(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    positionen = [
        _POS_S,
        {"beschreibung": "Material 7", "einzelpreis": "3.50", "steuer_satz": "7"},
        _POS_Z,
        _POS_AE,
        _POS_E,
        {**_POS_E, "steuer_grund_text": "Steuerfreie Leistung nach § 4 Nr. 8 UStG", "einzelpreis": "10"},
    ]
    xml = await _versendet_xml(client, token, kunde, positionen)
    _pruefe_en16931(xml, tmp_path, "alle_kategorien")


@pytest.mark.asyncio
async def test_kleinunternehmer(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten={**_E_RECHNUNG, "ist_kleinunternehmer": True, "ust_idnr": None, "steuernummer": "12/345/67890"},
    )
    xml = await _versendet_xml(client, token, kunde, [_POS_S, {"beschreibung": "Arbeit", "menge": "2.5", "einzelpreis": "55"}])
    _pruefe_en16931(xml, tmp_path, "kleinunternehmer")


@pytest.mark.asyncio
async def test_storno(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    positionen = [
        _POS_S,
        {"beschreibung": "Material 7", "menge": "2", "einzelpreis": "3.50", "steuer_satz": "7"},
    ]
    original = await _rechnung(client, token, kunde, positionen)
    assert (await _versenden(client, token, original["id"])).status_code == 200
    storno = await client.post(f"/api/rechnungen/{original['id']}/storno", headers=auth_headers(token))
    assert storno.status_code == 201
    assert storno.json()["xml_object_key"] is not None
    xml = await client.get(f"/api/rechnungen/{storno.json()['id']}/xml", headers=auth_headers(token))
    assert xml.status_code == 200
    _pruefe_en16931(xml.content, tmp_path, "storno")


@pytest.mark.asyncio
async def test_storno_mit_allen_kategorien_und_rundung(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    positionen = [
        {"beschreibung": "Halb-Cent", "menge": "0.5", "einzelpreis": "10.01"},
        {"beschreibung": "Halb-Cent 2", "menge": "0.5", "einzelpreis": "10.01"},
        {"beschreibung": "Material 7", "menge": "3", "einzelpreis": "0.33", "steuer_satz": "7"},
        _POS_Z,
        _POS_AE,
        _POS_E,
    ]
    original = await _rechnung(client, token, kunde, positionen)
    assert (await _versenden(client, token, original["id"])).status_code == 200
    storno = await client.post(f"/api/rechnungen/{original['id']}/storno", headers=auth_headers(token))
    assert storno.status_code == 201
    xml = await client.get(f"/api/rechnungen/{storno.json()['id']}/xml", headers=auth_headers(token))
    _pruefe_en16931(xml.content, tmp_path, "storno_alle_kategorien")


@pytest.mark.asyncio
@pytest.mark.parametrize("typ", ["privat", "oeffentlich"])
async def test_kundentypen(client, make_mandant, make_user, make_kunde, tmp_path, typ):
    kunde_kw = {"typ": typ, "ust_idnr": None} if typ == "privat" else {"typ": typ}
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde, **kunde_kw)
    xml = await _versendet_xml(client, token, kunde, [_POS_S])
    _pruefe_en16931(xml, tmp_path, f"kunde_{typ}")


@pytest.mark.asyncio
async def test_mehrere_positionen_mit_rundungsrandfaellen(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    positionen = [
        {"beschreibung": "Halb-Cent", "menge": "0.5", "einzelpreis": "33.33"},
        {"beschreibung": "Drittel", "menge": "0.333", "einzelpreis": "10.10"},
        {"beschreibung": "Viele Stueck", "menge": "7", "einzelpreis": "0.07", "steuer_satz": "7"},
        {"beschreibung": "Bruchmenge", "menge": "1.25", "einzelpreis": "19.99", "steuer_satz": "7"},
        {"beschreibung": "Cent-Wert", "menge": "1", "einzelpreis": "0.01"},
        {"beschreibung": "Stundensatz", "menge": "2.75", "einzelpreis": "57.45"},
    ]
    xml = await _versendet_xml(client, token, kunde, positionen)
    _pruefe_en16931(xml, tmp_path, "rundung")


@pytest.mark.asyncio
async def test_rechnung_mit_faelligkeit(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_S], faellig_am="2026-09-10")
    assert b"2026-09-10" in xml.replace(b"20260910", b"2026-09-10")
    _pruefe_en16931(xml, tmp_path, "mit_faelligkeit")


@pytest.mark.asyncio
async def test_rechnung_ohne_faelligkeit(client, make_mandant, make_user, make_kunde, tmp_path):
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    xml = await _versendet_xml(client, token, kunde, [_POS_S])
    assert b"PaymentTerms" not in xml
    _pruefe_en16931(xml, tmp_path, "ohne_faelligkeit")


@pytest.mark.asyncio
async def test_rechnung_ohne_positionen(client, make_mandant, make_user, make_kunde, tmp_path):
    # Einfacher Fall aus Phase 6: nur Nettobetrag am Beleg, die Zeile entsteht synthetisch.
    token, kunde = await _admin_e_rechnung(client, make_mandant, make_user, make_kunde)
    rechnung = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "300.00", "mwst_satz": "19.00", "leistungsdatum": "2026-08-10"},
    )
    assert rechnung.status_code == 201, rechnung.text
    assert (await _versenden(client, token, rechnung.json()["id"])).status_code == 200
    xml = await client.get(f"/api/rechnungen/{rechnung.json()['id']}/xml", headers=auth_headers(token))
    _pruefe_en16931(xml.content, tmp_path, "ohne_positionen")
