"""Rechnungsarten (Migration 0108): Rechnung aus Angebot, Abschlag, Schlussrechnung
mit Anrechnung der Abschlaege, Gutschrift und die Offene-Posten-Regel."""
import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pymupdf
import pytest
from lxml import etree
from sqlalchemy import select, text

from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import mahnwesen_service, rechnung_service
from tests.conftest import auth_headers, login
from tests.test_kundenportal import _kunden_login, _make_zugang
from tests.test_steuer_freischaltung import _E_RECHNUNG, _KUNDE_E_RECHNUNG
from tests.test_steuer_je_position import _migrieren, _spalten, _sync_engine

# Angebot-Netto 1500,00 (19 %): zwei Positionen.
ANGEBOT_POSITIONEN = [
    {"beschreibung": "Photovoltaikanlage", "menge": "1", "einheit": "psch", "einzelpreis": "1000.00"},
    {"beschreibung": "Montage", "menge": "10", "einheit": "Std", "einzelpreis": "50.00", "positionstyp": "arbeitszeit"},
]
MISCH_POSITIONEN = [
    {"beschreibung": "Leistung 19", "menge": "1", "einheit": "psch", "einzelpreis": "1000.00"},
    {"beschreibung": "Material 7", "menge": "1", "einheit": "psch", "einzelpreis": "200.00", "steuer_satz": "7"},
]


def _d(wert) -> Decimal:
    return Decimal(str(wert))


async def _admin(client, make_mandant, make_user, make_kunde, *, firmendaten=None, mandant=None, **kunde_kw):
    mandant = mandant or await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, **kunde_kw)
    token = await login(client, admin.email, "pw-123456")
    h = auth_headers(token)
    if firmendaten is not None:
        resp = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": firmendaten})
        assert resp.status_code == 200, resp.text
    return mandant, kunde, h


async def _angebot(client, h, kunde, *, positionen=None, angenommen=True, **extra) -> dict:
    resp = await client.post(
        "/api/angebote",
        headers=h,
        json={"kunde_id": str(kunde.id), "positionen": positionen or ANGEBOT_POSITIONEN, **extra},
    )
    assert resp.status_code == 201, resp.text
    angebot = resp.json()
    if angenommen:
        for status in ("versendet", "angenommen"):
            resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": status})
            assert resp.status_code == 200, resp.text
        angebot = resp.json()
    return angebot


async def _aus_angebot(client, h, angebot_id, art, **extra):
    return await client.post(
        "/api/rechnungen/aus-angebot",
        headers=h,
        json={"angebot_id": angebot_id, "rechnungsart": art, "leistungsdatum": "2026-08-10", **extra},
    )


async def _ok(resp, status=201) -> dict:
    assert resp.status_code == status, resp.text
    return resp.json()


async def _versenden(client, h, rechnung_id) -> dict:
    return await _ok(await client.patch(f"/api/rechnungen/{rechnung_id}", headers=h, json={"status": "versendet"}), 200)


async def _abschlag(client, h, angebot_id, **extra) -> dict:
    return await _ok(await _aus_angebot(client, h, angebot_id, "abschlag", **extra))


async def _abschlag_versendet(client, h, angebot_id, **extra) -> dict:
    abschlag = await _abschlag(client, h, angebot_id, **extra)
    return await _versenden(client, h, abschlag["id"])


async def _rechnung_direkt(client, h, kunde, positionen, **extra) -> dict:
    return await _ok(
        await client.post(
            "/api/rechnungen",
            headers=h,
            json={
                "kunde_id": str(kunde.id),
                "mwst_satz": "19.00",
                "leistungsdatum": "2026-08-10",
                "positionen": positionen,
                **extra,
            },
        )
    )


async def _holen(client, h, rechnung_id) -> dict:
    return await _ok(await client.get(f"/api/rechnungen/{rechnung_id}", headers=h), 200)


async def _gutschrift(client, h, rechnung_id, **body):
    return await client.post(
        f"/api/rechnungen/{rechnung_id}/gutschrift", headers=h, json={"grund": "Preisnachlass vereinbart", **body}
    )


def _abzuege(rechnung: dict) -> list[dict]:
    return [p for p in rechnung["positionen"] if p["abschlag_rechnung_id"]]


# --- Rechnung aus Angebot ----------------------------------------------------------


async def test_rechnung_aus_angebot_voll(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    rechnung = await _ok(await _aus_angebot(client, h, angebot["id"], "rechnung", faellig_am="2026-09-01"))

    assert rechnung["rechnungsart"] == "rechnung"
    assert rechnung["angebot_id"] == angebot["id"]
    assert rechnung["status"] == "entwurf"
    assert rechnung["kunde_id"] == str(kunde.id)
    assert rechnung["vorgang_id"] == angebot["auftrag_vorgang_id"]
    assert rechnung["faellig_am"] == "2026-09-01"
    assert [(p["beschreibung"], p["menge"], p["einheit"], p["einzelpreis"]) for p in rechnung["positionen"]] == [
        ("Photovoltaikanlage", "1.00", "psch", "1000.00"),
        ("Montage", "10.00", "Std", "50.00"),
    ]
    assert all(p["steuer_kategorie"] == "S" and p["steuer_satz"] == "19.00" for p in rechnung["positionen"])
    assert rechnung["betrag_netto"] == "1500.00"
    assert rechnung["betrag_brutto"] == "1785.00"
    assert rechnung["offener_betrag"] == "1785.00"
    # Die Angebotsansicht kennt jetzt die Rechnung.
    angebot_neu = (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()
    assert angebot_neu["rechnung_id"] == rechnung["id"]
    assert angebot_neu["schlussrechnung_id"] is None and angebot_neu["abschlaege"] == []


async def test_rechnung_aus_angebot_mit_ermaessigtem_satz(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde, mwst_satz="7.00")
    rechnung = await _ok(await _aus_angebot(client, h, angebot["id"], "rechnung"))
    assert rechnung["mwst_satz"] == "7.00"
    assert rechnung["betrag_brutto"] == "1605.00"


async def test_rechnung_aus_angebot_kleinunternehmer(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten={"ist_kleinunternehmer": True})
    for art, extra in (("rechnung", {}), ("abschlag", {"abschlag_prozent": "50"})):
        angebot = await _angebot(client, h, kunde)
        assert angebot["mwst_satz"] == "0.00"
        rechnung = await _ok(await _aus_angebot(client, h, angebot["id"], art, **extra))
        assert rechnung["mwst_satz"] == "0.00"
        for p in rechnung["positionen"]:
            assert (p["steuer_kategorie"], p["steuer_satz"], p["steuer_grund"]) == ("E", "0.00", "kleinunternehmer_19")
        assert rechnung["betrag_steuer"] == "0.00"


async def test_rechnung_aus_angebot_nur_wenn_angenommen(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    entwurf = await _angebot(client, h, kunde, angenommen=False)
    resp = await _aus_angebot(client, h, entwurf["id"], "rechnung")
    assert resp.status_code == 400
    assert "angenommene" in resp.json()["detail"]


async def test_rechnung_aus_angebot_doppelt_ist_konflikt(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    erste = await _ok(await _aus_angebot(client, h, angebot["id"], "rechnung"))
    zweite = await _aus_angebot(client, h, angebot["id"], "rechnung")
    assert zweite.status_code == 409
    assert erste["rechnungsnummer"] in zweite.json()["detail"]
    # Auch eine Schlussrechnung waere eine zweite Abrechnung desselben Angebots.
    assert (await _aus_angebot(client, h, angebot["id"], "schluss")).status_code == 409
    # Nach dem Loeschen des Entwurfs ist das Angebot wieder frei.
    assert (await client.delete(f"/api/rechnungen/{erste['id']}", headers=h)).status_code == 204
    await _ok(await _aus_angebot(client, h, angebot["id"], "rechnung"))


async def test_rechnung_nach_abschlag_ist_verboten(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag(client, h, angebot["id"], abschlag_prozent="30")
    resp = await _aus_angebot(client, h, angebot["id"], "rechnung")
    assert resp.status_code == 409
    assert "Schlussrechnung" in resp.json()["detail"]


async def test_aus_angebot_unbekannt_oder_fremd_ist_404(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    _, fremder_kunde, fremd_h = await _admin(client, make_mandant, make_user, make_kunde)
    fremdes_angebot = await _angebot(client, fremd_h, fremder_kunde)
    assert (await _aus_angebot(client, h, fremdes_angebot["id"], "rechnung")).status_code == 404
    assert (await _aus_angebot(client, h, str(uuid.uuid4()), "rechnung")).status_code == 404


# --- Abschlag --------------------------------------------------------------------


async def test_abschlag_in_prozent(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag(client, h, angebot["id"], abschlag_prozent="30")

    assert abschlag["rechnungsart"] == "abschlag"
    [position] = abschlag["positionen"]
    assert position["beschreibung"] == f"Abschlagszahlung 30 % auf Angebot {angebot['angebotsnummer']}"
    assert (position["menge"], position["einheit"], position["einzelpreis"]) == ("1.00", "psch", "450.00")
    assert abschlag["betrag_netto"] == "450.00" and abschlag["betrag_brutto"] == "535.50"


async def test_abschlag_in_prozent_rundet_kaufmaennisch(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    # 33,33 % von 100,50 = 33,4967 -> 33,50; 1 % von 0,50 = 0,005 ist ein Halb-Cent und wird aufgerundet.
    angebot = await _angebot(
        client, h, kunde, positionen=[{"beschreibung": "X", "menge": "1", "einheit": "psch", "einzelpreis": "100.50"}]
    )
    abschlag = await _abschlag(client, h, angebot["id"], abschlag_prozent="33.33")
    assert abschlag["positionen"][0]["einzelpreis"] == "33.50"
    assert "33,33 %" in abschlag["positionen"][0]["beschreibung"]
    klein = await _angebot(
        client, h, kunde, positionen=[{"beschreibung": "Y", "menge": "1", "einheit": "psch", "einzelpreis": "0.10"}]
    )
    halb = await _abschlag(client, h, klein["id"], abschlag_prozent="12.5")
    assert halb["positionen"][0]["einzelpreis"] == "0.01"  # 0,0125 -> 0,01
    halb2 = await _angebot(
        client, h, kunde, positionen=[{"beschreibung": "Z", "menge": "1", "einheit": "psch", "einzelpreis": "0.30"}]
    )
    assert (await _abschlag(client, h, halb2["id"], abschlag_prozent="50"))["positionen"][0]["einzelpreis"] == "0.15"
    tief = await _angebot(
        client, h, kunde, positionen=[{"beschreibung": "W", "menge": "1", "einheit": "psch", "einzelpreis": "0.50"}]
    )
    assert (await _abschlag(client, h, tief["id"], abschlag_prozent="1"))["positionen"][0]["einzelpreis"] == "0.01"


async def test_abschlag_als_nettobetrag(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag(client, h, angebot["id"], abschlag_netto="400.005")
    [position] = abschlag["positionen"]
    assert position["beschreibung"] == f"Abschlagszahlung auf Angebot {angebot['angebotsnummer']}"
    assert position["einzelpreis"] == "400.01"


async def test_abschlag_braucht_genau_eine_angabe(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    for extra in ({}, {"abschlag_prozent": "10", "abschlag_netto": "100"}):
        assert (await _aus_angebot(client, h, angebot["id"], "abschlag", **extra)).status_code == 422
    for extra in ({"abschlag_prozent": "0"}, {"abschlag_prozent": "100.01"}, {"abschlag_netto": "0"}, {"abschlag_netto": "-5"}):
        assert (await _aus_angebot(client, h, angebot["id"], "abschlag", **extra)).status_code == 422
    # Bei anderen Arten sind die Abschlagsfelder unzulaessig.
    assert (await _aus_angebot(client, h, angebot["id"], "rechnung", abschlag_prozent="10")).status_code == 422


async def test_abschlag_grenze_ist_kumulativ(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag(client, h, angebot["id"], abschlag_prozent="60")
    await _abschlag(client, h, angebot["id"], abschlag_netto="300")
    resp = await _aus_angebot(client, h, angebot["id"], "abschlag", abschlag_prozent="21")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "mehr als 100 % des Angebots" in detail
    assert "bereits abgerechnet: 1.200,00 €" in detail and "Rest: 300,00 €" in detail
    # Genau der Rest ist erlaubt (auch nicht versendete Abschlaege belegen Kontingent).
    await _abschlag(client, h, angebot["id"], abschlag_netto="300")
    assert (await _aus_angebot(client, h, angebot["id"], "abschlag", abschlag_netto="0.01")).status_code == 422
    angebot_neu = (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()
    assert angebot_neu["abgerechnet_netto"] == "1500.00" and angebot_neu["rest_netto"] == "0.00"
    assert [a["netto"] for a in angebot_neu["abschlaege"]] == ["900.00", "300.00", "300.00"]
    assert {a["status"] for a in angebot_neu["abschlaege"]} == {"entwurf"}


async def test_stornierter_abschlag_gibt_kontingent_frei(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="100")
    assert (await _aus_angebot(client, h, angebot["id"], "abschlag", abschlag_prozent="1")).status_code == 422
    storno = await client.post(f"/api/rechnungen/{abschlag['id']}/storno", headers=h)
    assert storno.status_code == 201, storno.text
    await _abschlag(client, h, angebot["id"], abschlag_prozent="100")


async def test_abschlag_parallel_ueberschreitet_nicht_100_prozent(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    antworten = await asyncio.gather(
        *[_aus_angebot(client, h, angebot["id"], "abschlag", abschlag_prozent="60") for _ in range(3)]
    )
    assert sorted(r.status_code for r in antworten) == [201, 422, 422]
    angebot_neu = (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()
    assert angebot_neu["abgerechnet_netto"] == "900.00"


async def test_abschlag_nach_schlussrechnung_ist_konflikt(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    resp = await _aus_angebot(client, h, angebot["id"], "abschlag", abschlag_prozent="10")
    assert resp.status_code == 409
    assert schluss["rechnungsnummer"] in resp.json()["detail"]


async def test_abschlag_ohne_angebot_mit_manueller_position(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    abschlag = await _rechnung_direkt(
        client,
        h,
        kunde,
        [{"beschreibung": "Abschlag Heizung", "einzelpreis": "500"}],
        rechnungsart="abschlag",
    )
    assert abschlag["rechnungsart"] == "abschlag" and abschlag["angebot_id"] is None
    # Schluss und Gutschrift sind ueber die Anlage nicht waehlbar.
    for art in ("schluss", "gutschrift", "quatsch"):
        resp = await client.post(
            "/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "rechnungsart": art, "positionen": []}
        )
        assert resp.status_code == 422, art


# --- Schlussrechnung ---------------------------------------------------------------


async def test_schluss_ohne_abschlag(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    assert schluss["rechnungsart"] == "schluss" and schluss["angerechnete_abschlaege"] == []
    assert schluss["betrag_netto"] == "1500.00" and schluss["betrag_brutto"] == "1785.00"
    angebot_neu = (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()
    assert angebot_neu["schlussrechnung_id"] == schluss["id"]


async def test_schluss_mit_einem_abschlag(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))

    [abzug] = _abzuege(schluss)
    assert abzug["abschlag_rechnung_id"] == abschlag["id"]
    assert abzug["beschreibung"] == (
        f"Abzüglich Abschlagsrechnung {abschlag['rechnungsnummer']} vom "
        f"{date.today().strftime('%d.%m.%Y')} (netto)"
    )
    assert (abzug["menge"], abzug["einheit"], abzug["einzelpreis"]) == ("1.00", "psch", "-450.00")
    assert (abzug["steuer_kategorie"], abzug["steuer_satz"]) == ("S", "19.00")
    assert schluss["betrag_netto"] == "1050.00"  # Angebot 1500 - Abschlag 450
    assert schluss["betrag_steuer"] == "199.50"
    assert schluss["betrag_brutto"] == "1249.50"
    assert [(a["rechnung_id"], a["netto"]) for a in schluss["angerechnete_abschlaege"]] == [(abschlag["id"], "450.00")]
    # Abschlag-Brutto + Rest ergeben das Angebot-Brutto.
    assert _d(abschlag["betrag_brutto"]) + _d(schluss["betrag_brutto"]) == _d(angebot["gesamt_brutto"])


async def test_schluss_mit_zwei_abschlaegen_und_entwurf_blockiert(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    a1 = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    a2 = await _abschlag(client, h, angebot["id"], abschlag_netto="200")

    resp = await _aus_angebot(client, h, angebot["id"], "schluss")
    assert resp.status_code == 409
    assert resp.json()["detail"] == f"Abschlag {a2['rechnungsnummer']} ist noch nicht versendet"

    await _versenden(client, h, a2["id"])
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    assert [a["rechnung_id"] for a in schluss["angerechnete_abschlaege"]] == [a1["id"], a2["id"]]
    assert schluss["betrag_netto"] == "850.00"  # 1500 - 450 - 200
    assert schluss["betrag_brutto"] == "1011.50"
    assert [p["einzelpreis"] for p in _abzuege(schluss)] == ["-450.00", "-200.00"]


async def test_schluss_rechnet_abschlag_nur_einmal_an(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    # Ein zweiter Entwurf (manuell, gleiche Vorgangsbasis) darf denselben Abschlag nicht nochmal anrechnen.
    zweiter = await _rechnung_direkt(
        client, h, kunde, [{"beschreibung": "Nachtrag", "einzelpreis": "50"}], vorgang_id=angebot["auftrag_vorgang_id"]
    )
    resp = await client.post(f"/api/rechnungen/{zweiter['id']}/abschlaege-anrechnen", headers=h, json={})
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/rechnungen/{zweiter['id']}/abschlaege-anrechnen",
        headers=h,
        json={"abschlag_rechnung_ids": [abschlag["id"]]},
    )
    assert resp.status_code == 409
    assert schluss["rechnungsnummer"] in resp.json()["detail"]
    # Wird die Schlussrechnung (Entwurf) geloescht, ist der Abschlag wieder frei.
    assert (await client.delete(f"/api/rechnungen/{schluss['id']}", headers=h)).status_code == 204
    angerechnet = await _ok(
        await client.post(f"/api/rechnungen/{zweiter['id']}/abschlaege-anrechnen", headers=h, json={}), 200
    )
    assert angerechnet["rechnungsart"] == "schluss"


async def test_schluss_mischsteuer_abschlaege_getrennt_nach_steuersatz(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    """Abschlaege mit 19 % und mit 7 % in einer Schlussrechnung (aus einem Vorgang)."""
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    vorgang = {"id": str((await make_vorgang(mandant=mandant, kunde=kunde, titel="Umbau")).id)}
    a19 = await _rechnung_direkt(
        client, h, kunde, [{"beschreibung": "Abschlag 19", "einzelpreis": "500"}], rechnungsart="abschlag", vorgang_id=vorgang["id"]
    )
    a7 = await _rechnung_direkt(
        client,
        h,
        kunde,
        [{"beschreibung": "Abschlag 7", "einzelpreis": "300", "steuer_satz": "7"}],
        rechnungsart="abschlag",
        vorgang_id=vorgang["id"],
    )
    for a in (a19, a7):
        await _versenden(client, h, a["id"])
    schluss = await _rechnung_direkt(client, h, kunde, MISCH_POSITIONEN, vorgang_id=vorgang["id"])
    assert schluss["betrag_brutto"] == "1404.00"  # 1000*1,19 + 200*1,07
    schluss = await _ok(await client.post(f"/api/rechnungen/{schluss['id']}/abschlaege-anrechnen", headers=h, json={}), 200)

    abzuege = {p["abschlag_rechnung_id"]: p for p in _abzuege(schluss)}
    assert (abzuege[a19["id"]]["steuer_satz"], abzuege[a19["id"]]["einzelpreis"]) == ("19.00", "-500.00")
    assert (abzuege[a7["id"]]["steuer_satz"], abzuege[a7["id"]]["einzelpreis"]) == ("7.00", "-300.00")
    gruppen = {g["satz"]: (g["netto"], g["steuer"]) for g in schluss["steuergruppen"]}
    assert gruppen == {"19.00": ("500.00", "95.00"), "7.00": ("-100.00", "-7.00")}
    assert schluss["betrag_netto"] == "400.00"
    assert schluss["betrag_brutto"] == "488.00"  # 595 + (-107)
    # Brutto der Abschlaege (595 + 321) + Schluss ergibt das Brutto der Leistung (1404).
    assert _d(a19["betrag_brutto"]) + _d(a7["betrag_brutto"]) + _d(schluss["betrag_brutto"]) == Decimal("1404.00")


# --- Anrechnen an beliebigem Entwurf --------------------------------------------------


async def test_abschlaege_anrechnen_ueber_vorgang(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    vorgang = {"id": str((await make_vorgang(mandant=mandant, kunde=kunde, titel="Umbau")).id)}
    abschlag = await _rechnung_direkt(
        client, h, kunde, [{"beschreibung": "Anzahlung", "einzelpreis": "400"}], rechnungsart="abschlag", vorgang_id=vorgang["id"]
    )
    entwurf = await _rechnung_direkt(client, h, kunde, [{"beschreibung": "Arbeit", "einzelpreis": "1000"}], vorgang_id=vorgang["id"])
    # Abschlag im Entwurf: keine passenden (versendeten) Abschlaege, mit Hinweis.
    resp = await client.post(f"/api/rechnungen/{entwurf['id']}/abschlaege-anrechnen", headers=h, json={})
    assert resp.status_code == 409
    assert "Keine anrechenbaren" in resp.json()["detail"] and abschlag["rechnungsnummer"] in resp.json()["detail"]

    await _versenden(client, h, abschlag["id"])
    schluss = await _ok(await client.post(f"/api/rechnungen/{entwurf['id']}/abschlaege-anrechnen", headers=h), 200)
    assert schluss["rechnungsart"] == "schluss"
    assert schluss["betrag_netto"] == "600.00"
    [abzug] = _abzuege(schluss)

    # Abzug entfernen hebt die Anrechnung auf; der Abschlag ist danach wieder anrechenbar.
    ohne = await _ok(
        await client.delete(f"/api/rechnungen/{schluss['id']}/positionen/{abzug['id']}", headers=h), 200
    )
    assert ohne["betrag_netto"] == "1000.00" and ohne["angerechnete_abschlaege"] == []
    wieder = await _ok(await client.post(f"/api/rechnungen/{schluss['id']}/abschlaege-anrechnen", headers=h), 200)
    assert wieder["betrag_netto"] == "600.00"
    # Nochmal: nichts mehr anzurechnen.
    assert (await client.post(f"/api/rechnungen/{schluss['id']}/abschlaege-anrechnen", headers=h)).status_code == 409


async def test_abschlaege_anrechnen_ueber_angebot_und_gezielte_auswahl(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    a1 = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="10")
    a2 = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="20")
    # Manueller Entwurf, der nur ueber das Angebot (nicht ueber den Vorgang) zugeordnet ist.
    async with system_session() as session:
        quelle = await session.get(Angebot, uuid.UUID(angebot["id"]))
        entwurf = Rechnung(
            mandant_id=quelle.mandant_id,
            kunde_id=kunde.id,
            rechnungsnummer="X-ENTWURF-1",
            betrag_netto=Decimal("0"),
            mwst_satz=Decimal("19"),
            erstellt_von=quelle.erstellt_von,
            angebot_id=quelle.id,
        )
        session.add(entwurf)
        await session.flush()
        session.add(
            RechnungPosition(
                mandant_id=entwurf.mandant_id,
                rechnung_id=entwurf.id,
                position=1,
                beschreibung="Rest",
                menge=Decimal("1"),
                einheit="psch",
                einzelpreis=Decimal("1000"),
                steuer_kategorie="S",
                steuer_satz=Decimal("19"),
            )
        )
        await session.commit()
        entwurf_id = str(entwurf.id)
    schluss = await _ok(
        await client.post(
            f"/api/rechnungen/{entwurf_id}/abschlaege-anrechnen", headers=h, json={"abschlag_rechnung_ids": [a2["id"]]}
        ),
        200,
    )
    assert [a["rechnung_id"] for a in schluss["angerechnete_abschlaege"]] == [a2["id"]]
    assert schluss["betrag_netto"] == "700.00"
    # Ein fremder/unpassender Abschlag in der Auswahl ist ein Fehler.
    assert (
        await client.post(
            f"/api/rechnungen/{entwurf_id}/abschlaege-anrechnen",
            headers=h,
            json={"abschlag_rechnung_ids": [str(uuid.uuid4())]},
        )
    ).status_code == 422
    rest = await _ok(await client.post(f"/api/rechnungen/{entwurf_id}/abschlaege-anrechnen", headers=h), 200)
    assert sorted(a["rechnung_id"] for a in rest["angerechnete_abschlaege"]) == sorted([a1["id"], a2["id"]])


async def test_abschlaege_anrechnen_nur_im_entwurf_und_fuer_rechnung_oder_schluss(
    client, make_mandant, make_user, make_kunde
):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    versendet = await _versenden(
        client, h, (await _rechnung_direkt(client, h, kunde, [{"beschreibung": "A", "einzelpreis": "10"}]))["id"]
    )
    assert (await client.post(f"/api/rechnungen/{versendet['id']}/abschlaege-anrechnen", headers=h)).status_code == 400
    abschlag = await _rechnung_direkt(
        client, h, kunde, [{"beschreibung": "A", "einzelpreis": "10"}], rechnungsart="abschlag"
    )
    assert (await client.post(f"/api/rechnungen/{abschlag['id']}/abschlaege-anrechnen", headers=h)).status_code == 400


async def test_abzugsposition_ist_nicht_aenderbar(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    [abzug] = _abzuege(schluss)
    for body in ({"einzelpreis": "10"}, {"beschreibung": "x"}, {"steuer_satz": "7"}):
        resp = await client.patch(f"/api/rechnungen/{schluss['id']}/positionen/{abzug['id']}", headers=h, json=body)
        assert resp.status_code == 409, body


async def test_versendete_schlussrechnung_bleibt_unveraenderlich(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    versendet = await _versenden(client, h, schluss["id"])
    [abzug] = _abzuege(versendet)
    assert (
        await client.delete(f"/api/rechnungen/{schluss['id']}/positionen/{abzug['id']}", headers=h)
    ).status_code == 400
    assert (await client.post(f"/api/rechnungen/{schluss['id']}/abschlaege-anrechnen", headers=h)).status_code == 400


async def test_abschlag_mit_angerechneter_schlussrechnung_ist_nicht_stornierbar(
    client, make_mandant, make_user, make_kunde
):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _ok(await _aus_angebot(client, h, angebot["id"], "schluss"))
    # Schon der Entwurf der Schlussrechnung sperrt den Storno des Abschlags.
    resp = await client.post(f"/api/rechnungen/{abschlag['id']}/storno", headers=h)
    assert resp.status_code == 409
    assert schluss["rechnungsnummer"] in resp.json()["detail"]
    # Nach Storno der (versendeten) Schlussrechnung geht es wieder.
    await _versenden(client, h, schluss["id"])
    assert (await client.post(f"/api/rechnungen/{schluss['id']}/storno", headers=h)).status_code == 201
    assert (await client.post(f"/api/rechnungen/{abschlag['id']}/storno", headers=h)).status_code == 201


# --- Gutschrift --------------------------------------------------------------------

# 19 %: 10 x 100 = 1000 netto, Brutto 1190; eine Menge von 1 entspricht 119,00 Brutto.
EINZEL_POSITION = [{"beschreibung": "Anlage", "menge": "10", "einheit": "Stk", "einzelpreis": "100.00"}]
GRUPPEN_POSITIONEN = [
    {"beschreibung": "Leistung", "menge": "4", "einheit": "Std", "einzelpreis": "100.00"},
    {"beschreibung": "Material 7", "menge": "2", "einheit": "Stk", "einzelpreis": "50.00", "steuer_satz": "7"},
    {
        "beschreibung": "PV-Modul",
        "menge": "3",
        "einheit": "Stk",
        "einzelpreis": "200.00",
        "steuer_kategorie": "Z",
        "steuer_grund": "pv_12_3",
    },
]


async def _versendete_rechnung(client, h, kunde, positionen=None, **extra) -> dict:
    rechnung = await _rechnung_direkt(client, h, kunde, positionen or EINZEL_POSITION, **extra)
    return await _versenden(client, h, rechnung["id"])


async def _zahlung(client, h, rechnung_id, betrag) -> dict:
    return await _ok(
        await client.post(f"/api/rechnungen/{rechnung_id}/zahlungen", headers=h, json={"betrag": str(betrag)}), 201
    )


async def _op_regel_sql_gleich_python(mandant) -> dict[uuid.UUID, Decimal]:
    """Die eine Regel in zwei Gestalten: offen_sql() und offene_betraege() muessen
    fuer jede Rechnung des Mandanten dasselbe liefern."""
    async with system_session() as session:
        sql = {
            rid: offen.quantize(Decimal("0.01"))
            for rid, offen in (
                await session.execute(
                    select(Rechnung.id, rechnung_service.offen_sql()).where(Rechnung.mandant_id == mandant.id)
                )
            ).all()
        }
        rechnungen = list(
            (await session.execute(select(Rechnung).where(Rechnung.mandant_id == mandant.id))).scalars().all()
        )
        python = await rechnung_service.offene_betraege(session, rechnungen)
    assert sql == python
    return python


async def test_gutschrift_teilweise_mit_mehreren_steuergruppen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde, GRUPPEN_POSITIONEN, leistungsdatum="2026-07-15")
    leistung, material, pv = original["positionen"]

    gutschrift = await _ok(
        await _gutschrift(
            client,
            h,
            original["id"],
            positionen=[{"position_id": leistung["id"], "menge": "1"}, {"position_id": material["id"], "menge": "2"}],
        )
    )
    assert gutschrift["rechnungsart"] == "gutschrift"
    assert gutschrift["bezug_rechnung_id"] == original["id"]
    assert gutschrift["status"] == "versendet" and gutschrift["ist_storno"] is False
    assert gutschrift["gutschrift_grund"] == "Preisnachlass vereinbart"
    assert gutschrift["leistungsdatum"] == "2026-07-15"
    assert gutschrift["rechnungsnummer"].startswith("R-") and gutschrift["rechnungsnummer"] != original["rechnungsnummer"]
    assert gutschrift["faellig_am"] is None
    assert [
        (p["beschreibung"], p["menge"], p["einzelpreis"], p["steuer_kategorie"], p["steuer_satz"], p["bezug_position_id"])
        for p in gutschrift["positionen"]
    ] == [
        ("Leistung", "1.00", "-100.00", "S", "19.00", leistung["id"]),
        ("Material 7", "2.00", "-50.00", "S", "7.00", material["id"]),
    ]
    gruppen = {g["satz"]: (g["netto"], g["steuer"]) for g in gutschrift["steuergruppen"]}
    assert gruppen == {"19.00": ("-100.00", "-19.00"), "7.00": ("-100.00", "-7.00")}
    assert gutschrift["betrag_netto"] == "-200.00" and gutschrift["betrag_brutto"] == "-226.00"

    # Original: bleibt gueltig, kennt die Gutschrift und die gutgeschriebenen Mengen.
    neu = await _holen(client, h, original["id"])
    assert neu["status"] == "versendet"
    assert [(g["rechnung_id"], g["brutto"]) for g in neu["gutschriften"]] == [(gutschrift["id"], "-226.00")]
    assert [p["bereits_gutgeschrieben"] for p in neu["positionen"]] == ["1.00", "2.00", "0.00"]
    assert _d(neu["offener_betrag"]) == _d(original["betrag_brutto"]) - Decimal("226.00")
    # Das PDF der Gutschrift entsteht und die Gutschrift ist archiviert.
    assert (await client.get(f"/api/rechnungen/{gutschrift['id']}/pdf", headers=h)).content.startswith(b"%PDF")


async def test_gutschrift_alle_positionen_und_status_bezahlt(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde, GRUPPEN_POSITIONEN)
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True))
    assert len(gutschrift["positionen"]) == 3
    assert gutschrift["betrag_netto"] == "-" + original["betrag_netto"]
    assert gutschrift["betrag_brutto"] == "-" + original["betrag_brutto"]
    neu = await _holen(client, h, original["id"])
    assert neu["status"] == "bezahlt" and neu["bezahlt_am"] is not None
    assert neu["offener_betrag"] == "0.00"
    # Nichts mehr gutzuschreiben.
    assert (await _gutschrift(client, h, original["id"], alle=True)).status_code == 422


async def test_gutschrift_mengengrenze_ist_kumulativ(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    position = original["positionen"][0]  # Menge 10
    await _ok(await _gutschrift(client, h, original["id"], positionen=[{"position_id": position["id"], "menge": "6"}]))
    zu_viel = await _gutschrift(client, h, original["id"], positionen=[{"position_id": position["id"], "menge": "4.01"}])
    assert zu_viel.status_code == 422
    assert "noch gutschreibbare Menge 4.00" in zu_viel.json()["detail"]
    await _ok(await _gutschrift(client, h, original["id"], positionen=[{"position_id": position["id"], "menge": "4"}]))
    assert (
        await _gutschrift(client, h, original["id"], positionen=[{"position_id": position["id"], "menge": "0.01"}])
    ).status_code == 422
    assert len((await _holen(client, h, original["id"]))["gutschriften"]) == 2


async def test_gutschrift_parallel_ueberschreitet_menge_nicht(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    position = original["positionen"][0]
    antworten = await asyncio.gather(
        *[
            _gutschrift(client, h, original["id"], positionen=[{"position_id": position["id"], "menge": "6"}])
            for _ in range(3)
        ]
    )
    assert sorted(r.status_code for r in antworten) == [201, 422, 422]


async def test_gutschrift_voraussetzungen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    entwurf = await _rechnung_direkt(client, h, kunde, EINZEL_POSITION)
    assert (await _gutschrift(client, h, entwurf["id"], alle=True)).status_code == 409

    original = await _versenden(client, h, entwurf["id"])
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True))
    # Gutschrift auf Gutschrift.
    assert (await _gutschrift(client, h, gutschrift["id"], alle=True)).status_code == 409

    # Gutschrift auf einen Storno-Beleg.
    zweite = await _versendete_rechnung(client, h, kunde)
    storno = await _ok(await client.post(f"/api/rechnungen/{zweite['id']}/storno", headers=h))
    assert (await _gutschrift(client, h, storno["id"], alle=True)).status_code == 409
    # Das stornierte Original selbst ist ebenfalls kein Gutschrift-Kandidat.
    assert (await _gutschrift(client, h, zweite["id"], alle=True)).status_code == 409


async def test_gutschrift_auf_abschlag_ist_nicht_moeglich(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    resp = await _gutschrift(client, h, abschlag["id"], alle=True)
    assert resp.status_code == 409 and "Abschlagsrechnung" in resp.json()["detail"]


async def test_gutschrift_eingaben_werden_geprueft(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    position_id = original["positionen"][0]["id"]
    auswahl = [{"position_id": position_id, "menge": "1"}]
    url = f"/api/rechnungen/{original['id']}/gutschrift"
    assert (await client.post(url, headers=h, json={"grund": "Grund ok"})).status_code == 422  # weder noch
    assert (
        await client.post(url, headers=h, json={"grund": "Grund ok", "alle": True, "positionen": auswahl})
    ).status_code == 422
    assert (await client.post(url, headers=h, json={"grund": "ab", "alle": True})).status_code == 422
    assert (await client.post(url, headers=h, json={"grund": "x" * 201, "alle": True})).status_code == 422
    nullmenge = {"grund": "Grund ok", "positionen": [{"position_id": position_id, "menge": "0"}]}
    assert (await client.post(url, headers=h, json=nullmenge)).status_code == 422
    fremd = {"grund": "Grund ok", "positionen": [{"position_id": str(uuid.uuid4()), "menge": "1"}]}
    assert (await client.post(url, headers=h, json=fremd)).status_code == 422
    doppelt = {"grund": "Grund ok", "positionen": auswahl + auswahl}
    assert (await client.post(url, headers=h, json=doppelt)).status_code == 422
    assert (await client.post(url, headers=h, json={"grund": "Grund ok", "alle": False})).status_code == 422


async def test_gutschrift_muss_betrag_verringern(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    [abzug] = _abzuege(schluss)
    # Die Gutschrift allein auf die Abzugsposition waere eine Belastung.
    resp = await _gutschrift(client, h, schluss["id"], positionen=[{"position_id": abzug["id"], "menge": "1"}])
    assert resp.status_code == 422 and "negativen Gesamtbetrag" in resp.json()["detail"]
    # Alle Positionen der Schlussrechnung ergeben eine Gutschrift ueber den Restbetrag.
    gutschrift = await _ok(await _gutschrift(client, h, schluss["id"], alle=True))
    assert gutschrift["betrag_netto"] == "-1050.00"


async def test_gutschrift_zu_rechnung_ohne_positionen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    einfach = await _ok(
        await client.post(
            "/api/rechnungen",
            headers=h,
            json={"kunde_id": str(kunde.id), "betrag_netto": "300.00", "mwst_satz": "19.00", "leistungsdatum": "2026-08-10"},
        )
    )
    einfach = await _versenden(client, h, einfach["id"])
    positionsweise = await _gutschrift(
        client, h, einfach["id"], positionen=[{"position_id": str(uuid.uuid4()), "menge": "1"}]
    )
    assert positionsweise.status_code == 422
    gutschrift = await _ok(await _gutschrift(client, h, einfach["id"], alle=True))
    assert gutschrift["betrag_netto"] == "-300.00" and gutschrift["betrag_brutto"] == "-357.00"
    assert (await _gutschrift(client, h, einfach["id"], alle=True)).status_code == 409


async def test_komplett_storno_nach_gutschrift_ist_gesperrt(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    gutschrift = await _ok(
        await _gutschrift(
            client, h, original["id"], positionen=[{"position_id": original["positionen"][0]["id"], "menge": "1"}]
        )
    )
    resp = await client.post(f"/api/rechnungen/{original['id']}/storno", headers=h)
    assert resp.status_code == 409
    assert gutschrift["rechnungsnummer"] in resp.json()["detail"]
    # Wird die Gutschrift storniert, ist der Komplett-Storno wieder frei und das Original wieder offen.
    assert (await client.post(f"/api/rechnungen/{gutschrift['id']}/storno", headers=h)).status_code == 201
    assert (await _holen(client, h, original["id"]))["offener_betrag"] == original["betrag_brutto"]
    assert (await client.post(f"/api/rechnungen/{original['id']}/storno", headers=h)).status_code == 201


async def test_gutschrift_nicht_bezahlt_markierbar_und_ohne_zahlung(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True))
    bezahlt = await client.patch(f"/api/rechnungen/{gutschrift['id']}", headers=h, json={"status": "bezahlt"})
    assert bezahlt.status_code == 400
    zahlung = await client.post(f"/api/rechnungen/{gutschrift['id']}/zahlungen", headers=h, json={"betrag": "10"})
    assert zahlung.status_code == 400


# --- Offene Posten mit Gutschriften -----------------------------------------------------


async def test_op_regel_gutschrift_senkt_offenen_rest(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)  # Brutto 1190
    position_id = original["positionen"][0]["id"]
    gutschrift = await _ok(
        await _gutschrift(client, h, original["id"], positionen=[{"position_id": position_id, "menge": "3"}])
    )
    assert gutschrift["betrag_brutto"] == "-357.00"
    assert gutschrift["offener_betrag"] == "0.00"
    neu = await _holen(client, h, original["id"])
    assert neu["offener_betrag"] == "833.00" and neu["status"] == "versendet"
    werte = await _op_regel_sql_gleich_python(mandant)
    assert werte[uuid.UUID(original["id"])] == Decimal("833.00") and werte[uuid.UUID(gutschrift["id"])] == Decimal("0")

    # Zahlung ueber den Rest bis zur Grenze: 833 offen, mehr geht nicht.
    zu_viel = await client.post(f"/api/rechnungen/{original['id']}/zahlungen", headers=h, json={"betrag": "833.01"})
    assert zu_viel.status_code == 400
    bezahlt = await _zahlung(client, h, original["id"], "833.00")
    assert bezahlt["status"] == "bezahlt" and bezahlt["offener_betrag"] == "0.00"
    # bezahlter_betrag bleibt echtes Geld (ohne Gutschrift).
    assert bezahlt["bezahlter_betrag"] == "833.00"
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_teilzahlung_und_gutschrift(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    await _zahlung(client, h, original["id"], "500")
    position_id = original["positionen"][0]["id"]
    await _ok(await _gutschrift(client, h, original["id"], positionen=[{"position_id": position_id, "menge": "3"}]))
    neu = await _holen(client, h, original["id"])
    assert neu["offener_betrag"] == "333.00"  # 1190 - 500 - 357
    assert neu["status"] == "teilweise_bezahlt"
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_ueberhang_bleibt_als_guthaben_an_der_gutschrift(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    await _zahlung(client, h, original["id"], "1000")  # Rest 190
    position_id = original["positionen"][0]["id"]
    gutschrift = await _ok(
        await _gutschrift(client, h, original["id"], positionen=[{"position_id": position_id, "menge": "3"}])
    )
    # 357 Gutschrift, nur 190 offen -> 167 Guthaben an der Gutschrift, Original bezahlt.
    assert gutschrift["offener_betrag"] == "-167.00"
    neu = await _holen(client, h, original["id"])
    assert neu["offener_betrag"] == "0.00" and neu["status"] == "bezahlt"
    werte = await _op_regel_sql_gleich_python(mandant)
    assert werte[uuid.UUID(gutschrift["id"])] == Decimal("-167.00")

    # Komplett bezahltes Original: die ganze Gutschrift ist Guthaben.
    zweites = await _versendete_rechnung(client, h, kunde)
    await _zahlung(client, h, zweites["id"], "1190")
    zweite_gs = await _ok(
        await _gutschrift(
            client, h, zweites["id"], positionen=[{"position_id": zweites["positionen"][0]["id"], "menge": "1"}]
        )
    )
    assert zweite_gs["offener_betrag"] == "-119.00"
    assert (await _holen(client, h, zweites["id"]))["status"] == "bezahlt"
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_mehrere_gutschriften_fruehere_nehmen_den_rest_zuerst(
    client, make_mandant, make_user, make_kunde
):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    await _zahlung(client, h, original["id"], "1000")  # Rest 190
    position_id = original["positionen"][0]["id"]
    eins = [{"position_id": position_id, "menge": "1"}]
    erste = await _ok(await _gutschrift(client, h, original["id"], positionen=eins))
    zweite = await _ok(await _gutschrift(client, h, original["id"], positionen=eins))
    dritte = await _ok(await _gutschrift(client, h, original["id"], positionen=eins))
    # 119 -> voll vom Rest (71 bleiben), 119 -> 71 absorbiert, 48 Guthaben; 119 -> komplett Guthaben.
    assert (erste["offener_betrag"], zweite["offener_betrag"], dritte["offener_betrag"]) == ("0.00", "-48.00", "-119.00")
    assert (await _holen(client, h, original["id"]))["offener_betrag"] == "0.00"
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_storno_beleg(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    unbezahlt = await _versendete_rechnung(client, h, kunde)
    storno = await _ok(await client.post(f"/api/rechnungen/{unbezahlt['id']}/storno", headers=h))
    # Ein Storno einer unbezahlten Rechnung hinterlaesst keinen offenen Posten (weder Forderung noch Guthaben).
    assert storno["offener_betrag"] == "0.00"

    bezahlt = await _versendete_rechnung(client, h, kunde)
    await _zahlung(client, h, bezahlt["id"], "400")
    storno2 = await _ok(await client.post(f"/api/rechnungen/{bezahlt['id']}/storno", headers=h))
    assert storno2["offener_betrag"] == "-400.00"  # 400 gezahlt -> 400 Guthaben
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_gutschrift_storno_macht_original_wieder_offen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True))
    assert (await _holen(client, h, original["id"]))["status"] == "bezahlt"
    storno = await _ok(await client.post(f"/api/rechnungen/{gutschrift['id']}/storno", headers=h))
    assert storno["rechnungsart"] == "rechnung" and storno["ist_storno"] is True
    # Der Storno einer Gutschrift ist (positiv) wieder eine normale Forderung.
    assert storno["offener_betrag"] == "1190.00"
    wieder = await _holen(client, h, original["id"])
    assert wieder["status"] == "versendet" and wieder["bezahlt_am"] is None and wieder["offener_betrag"] == "1190.00"
    # Die Gutschrift selbst ist storniert und hinterlaesst nichts.
    assert (await _holen(client, h, gutschrift["id"]))["status"] == "storniert"
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_uebersicht_summe_und_nur_offen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    teil = await _versendete_rechnung(client, h, kunde)  # 1190, Gutschrift 357 -> 833 offen
    position_id = teil["positionen"][0]["id"]
    await _ok(await _gutschrift(client, h, teil["id"], positionen=[{"position_id": position_id, "menge": "3"}]))
    voll = await _versendete_rechnung(client, h, kunde)  # vollstaendig gutgeschrieben -> verrechnet
    voll_gs = await _ok(await _gutschrift(client, h, voll["id"], alle=True))
    paid = await _versendete_rechnung(client, h, kunde)  # voll bezahlt + Gutschrift -> Guthaben
    await _zahlung(client, h, paid["id"], "1190")
    guthaben = await _ok(
        await _gutschrift(client, h, paid["id"], positionen=[{"position_id": paid["positionen"][0]["id"], "menge": "1"}])
    )

    offen = (await client.get("/api/rechnungen?nur_offen=true&limit=200", headers=h)).json()
    ids = {e["id"] for e in offen["eintraege"]}
    # Offen: die teilgutgeschriebene Rechnung und die Gutschrift mit Guthaben; nicht die verrechneten.
    assert ids == {teil["id"], guthaben["id"]}
    assert voll["id"] not in ids and voll_gs["id"] not in ids and paid["id"] not in ids
    assert offen["summe_offen"] == "714.00"  # 833 - 119 Guthaben
    alle = (await client.get("/api/rechnungen?limit=200", headers=h)).json()
    assert alle["summe_offen"] == "714.00"
    nach_art = (await client.get("/api/rechnungen?rechnungsart=gutschrift&limit=200", headers=h)).json()
    assert nach_art["gesamt_anzahl"] == 3 and {e["rechnungsart"] for e in nach_art["eintraege"]} == {"gutschrift"}
    await _op_regel_sql_gleich_python(mandant)


async def test_op_regel_op_liste_und_insights(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    teil = await _versendete_rechnung(client, h, kunde, faellig_am=str(date.today() + timedelta(days=5)))
    position_id = teil["positionen"][0]["id"]
    await _ok(await _gutschrift(client, h, teil["id"], positionen=[{"position_id": position_id, "menge": "3"}]))
    voll = await _versendete_rechnung(client, h, kunde)
    await _ok(await _gutschrift(client, h, voll["id"], alle=True))

    bericht = (await client.get("/api/auswertung/offene-posten", headers=h)).json()
    assert [(e["nummer"], e["offener_betrag"]) for e in bericht["debitoren"]] == [(teil["rechnungsnummer"], "833.00")]
    assert bericht["summe_debitoren"] == "833.00"
    insights = (await client.get("/api/insights", headers=h)).json()
    assert insights["offene_rechnungssumme"] == "833.00"


async def test_op_regel_mahnwesen_mahnt_nur_den_unverrechneten_rest(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    faellig = str(date.today() - timedelta(days=15))
    teil = await _versendete_rechnung(client, h, kunde, faellig_am=faellig)
    voll = await _versendete_rechnung(client, h, kunde, faellig_am=faellig)
    await _ok(
        await _gutschrift(client, h, teil["id"], positionen=[{"position_id": teil["positionen"][0]["id"], "menge": "3"}])
    )
    voll_gs = await _ok(await _gutschrift(client, h, voll["id"], alle=True))
    # Selbst eine ueberfaellig datierte Gutschrift wird nie gemahnt.
    async with system_session() as session:
        gs = await session.get(Rechnung, uuid.UUID(voll_gs["id"]))
        gs.faellig_am = date.today() - timedelta(days=40)
        await session.commit()

    ergebnis = await mahnwesen_service.run_mahnwesen_eskalation([mandant.id])
    assert ergebnis["rechnungen_eskaliert"] == 1
    async with system_session() as session:
        assert (await session.get(Rechnung, uuid.UUID(teil["id"]))).mahnstufe == 1
        assert (await session.get(Rechnung, uuid.UUID(voll["id"]))).mahnstufe == 0
        assert (await session.get(Rechnung, uuid.UUID(voll_gs["id"]))).mahnstufe == 0


# --- PDF und E-Rechnung ------------------------------------------------------------------

HINWEIS_ABSCHLAEGE = (
    "Bereits gestellte Abschlagsrechnungen wurden netto angerechnet; die Umsatzsteuer der Abschläge "
    "wurde bereits mit diesen Rechnungen ausgewiesen."
)


async def _pdf_text(client, h, rechnung_id) -> str:
    resp = await client.get(f"/api/rechnungen/{rechnung_id}/pdf", headers=h)
    assert resp.status_code == 200
    with pymupdf.open(stream=resp.content, filetype="pdf") as dokument:
        return " ".join(" ".join(seite.get_text() for seite in dokument).split())


async def test_pdf_ueberschrift_je_rechnungsart(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    normal = await _versendete_rechnung(client, h, kunde)
    text = await _pdf_text(client, h, normal["id"])
    assert "Rechnung Nr. " + normal["rechnungsnummer"] in text
    assert "Abschlagsrechnung" not in text and "Gutschrift" not in text and "Bereits gestellte" not in text

    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    assert "Abschlagsrechnung Nr. " + abschlag["rechnungsnummer"] in await _pdf_text(client, h, abschlag["id"])

    schluss = await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    text = await _pdf_text(client, h, schluss["id"])
    assert "Schlussrechnung Nr. " + schluss["rechnungsnummer"] in text
    assert f"Abzüglich Abschlagsrechnung {abschlag['rechnungsnummer']} vom" in text
    assert HINWEIS_ABSCHLAEGE in text
    assert "-450,00" in text or "-450.00" in text  # negative Abzugszeile

    gutschrift = await _ok(await _gutschrift(client, h, schluss["id"], alle=True, grund="Kulanz nach Reklamation"))
    text = await _pdf_text(client, h, gutschrift["id"])
    assert "Gutschrift Nr. " + gutschrift["rechnungsnummer"] in text
    assert f"Bezug: Rechnung {schluss['rechnungsnummer']} vom {date.today().strftime('%d.%m.%Y')}" in text
    assert "Grund: Kulanz nach Reklamation" in text
    # Die Gutschrift ueber die Schlussrechnung enthaelt auch die Abzugszeile -> Hinweis nur, wenn Abzuege vorkommen.
    assert "Bitte überweisen" not in text


async def test_pdf_schluss_ohne_abzuege_hat_keinen_hinweis(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    schluss = await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    text = await _pdf_text(client, h, schluss["id"])
    assert "Schlussrechnung Nr." in text and "Bereits gestellte" not in text


async def test_email_betreff_nennt_die_rechnungsart(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True))
    resp = await client.post(
        f"/api/rechnungen/{gutschrift['id']}/email", headers=h, json={"empfaenger": "kunde@example.de"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["betreff"] == f"Gutschrift {gutschrift['rechnungsnummer']}"
    assert gutschrift["rechnungsnummer"] in resp.json()["inhalt"] and "unsere Gutschrift" in resp.json()["inhalt"]


def _cii(xml: bytes):
    return etree.fromstring(xml)


async def _xml(client, h, rechnung_id) -> bytes:
    resp = await client.get(f"/api/rechnungen/{rechnung_id}/xml", headers=h)
    assert resp.status_code == 200, resp.text
    return resp.content


async def test_e_rechnung_typcodes_und_referenzen(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG, **_KUNDE_E_RECHNUNG
    )
    ns = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100", "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}

    def typcode(xml):
        return _cii(xml).findtext(".//rsm:ExchangedDocument/ram:TypeCode", namespaces=ns)

    normal = await _versendete_rechnung(client, h, kunde)
    assert typcode(await _xml(client, h, normal["id"])) == "380"

    angebot = await _angebot(client, h, kunde)
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    assert typcode(await _xml(client, h, abschlag["id"])) == "386"

    schluss = await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    xml = await _xml(client, h, schluss["id"])
    assert typcode(xml) == "380"
    # Mehrere Abschlaege lassen sich im EN16931-Profil nicht als Referenz ausdruecken -> Rechnungsvermerk.
    vermerke = [n.text for n in _cii(xml).findall(".//ram:IncludedNote/ram:Content", namespaces=ns)]
    assert any(abschlag["rechnungsnummer"] in v and v.startswith("Netto angerechnete") for v in vermerke)
    # Negative Abzugszeile: das Vorzeichen steckt in der Menge (BR-27), der Preis bleibt positiv.
    abzug_zeile = [z for z in _cii(xml).findall(".//ram:IncludedSupplyChainTradeLineItem", namespaces=ns) if "Abzüglich" in etree.tostring(z, encoding="unicode")]
    assert len(abzug_zeile) == 1
    assert abzug_zeile[0].findtext(".//ram:NetPriceProductTradePrice/ram:ChargeAmount", namespaces=ns) == "450.00"
    assert abzug_zeile[0].findtext(".//ram:BilledQuantity", namespaces=ns) == "-1.00"

    gutschrift = await _ok(await _gutschrift(client, h, normal["id"], alle=True, grund="Falsche Menge berechnet"))
    xml = await _xml(client, h, gutschrift["id"])
    assert typcode(xml) == "381"
    referenz = _cii(xml).find(".//ram:ApplicableHeaderTradeSettlement/ram:InvoiceReferencedDocument", namespaces=ns)
    assert referenz.findtext("ram:IssuerAssignedID", namespaces=ns) == normal["rechnungsnummer"]
    vermerke = [n.text for n in _cii(xml).findall(".//ram:IncludedNote/ram:Content", namespaces=ns)]
    assert "Grund der Gutschrift: Falsche Menge berechnet" in vermerke

    storno_original = await _versendete_rechnung(client, h, kunde)
    storno = await _ok(await client.post(f"/api/rechnungen/{storno_original['id']}/storno", headers=h))
    assert typcode(await _xml(client, h, storno["id"])) == "384"


# --- Rechte, Mandantentrennung, Portal --------------------------------------------------


async def test_neue_endpunkte_brauchen_das_recht_abrechnung_erstellen(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    original = await _versendete_rechnung(client, h, kunde)
    entwurf = await _rechnung_direkt(client, h, kunde, EINZEL_POSITION)
    for rolle in ("mitarbeiter", "controller"):  # keine Abrechnung bzw. nur "sehen"
        user = await make_user(mandant=mandant, role=rolle, password="pw-123456")
        kopf = auth_headers(await login(client, user.email, "pw-123456"))
        assert (await _aus_angebot(client, kopf, angebot["id"], "rechnung")).status_code == 403, rolle
        assert (await _gutschrift(client, kopf, original["id"], alle=True)).status_code == 403, rolle
        resp = await client.post(f"/api/rechnungen/{entwurf['id']}/abschlaege-anrechnen", headers=kopf)
        assert resp.status_code == 403, rolle
    # Der Disponent (abrechnung erstellen) darf.
    dispo = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kopf = auth_headers(await login(client, dispo.email, "pw-123456"))
    await _ok(await _aus_angebot(client, kopf, angebot["id"], "rechnung"))


async def test_fremde_rechnungen_und_abschlaege_sind_404_bzw_unzulaessig(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    _, fremder_kunde, fremd_h = await _admin(client, make_mandant, make_user, make_kunde)
    fremd = await _versendete_rechnung(client, fremd_h, fremder_kunde)
    fremd_entwurf = await _rechnung_direkt(client, fremd_h, fremder_kunde, EINZEL_POSITION)
    assert (await _gutschrift(client, h, fremd["id"], alle=True)).status_code == 404
    assert (await client.post(f"/api/rechnungen/{fremd_entwurf['id']}/abschlaege-anrechnen", headers=h)).status_code == 404

    # Ein Abschlag eines anderen Mandanten laesst sich nicht anrechnen.
    fremdes_angebot = await _angebot(client, fremd_h, fremder_kunde)
    fremder_abschlag = await _abschlag_versendet(client, fremd_h, fremdes_angebot["id"], abschlag_prozent="10")
    eigener = await _rechnung_direkt(client, h, kunde, EINZEL_POSITION)
    resp = await client.post(
        f"/api/rechnungen/{eigener['id']}/abschlaege-anrechnen",
        headers=h,
        json={"abschlag_rechnung_ids": [fremder_abschlag["id"]]},
    )
    assert resp.status_code in (409, 422)


async def test_portal_zeigt_gutschrift_und_rechnungsart(client, make_mandant, make_user, make_kunde):
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    original = await _versendete_rechnung(client, h, kunde)
    gutschrift = await _ok(await _gutschrift(client, h, original["id"], alle=True, grund="Kulanz Portal"))
    await _make_zugang(mandant, kunde, email="portal-gutschrift@example.de")
    tokens = await _kunden_login(client, "portal-gutschrift@example.de", "kunden-pw-123")
    kopf = auth_headers(tokens["access_token"])

    liste = (await client.get("/api/kundenportal/rechnungen", headers=kopf)).json()
    nach_id = {r["id"]: r for r in liste}
    assert nach_id[gutschrift["id"]]["rechnungsart"] == "gutschrift"
    assert nach_id[gutschrift["id"]]["gutschrift_grund"] == "Kulanz Portal"
    assert nach_id[gutschrift["id"]]["betrag_brutto"] == "-1190.00"
    assert nach_id[original["id"]]["offener_betrag"] == "0.00"  # durch Gutschrift verrechnet
    assert nach_id[original["id"]]["status"] == "bezahlt"
    for r in liste:  # keine internen Bezuege nach aussen
        assert "bezug_rechnung_id" not in r and "angebot_id" not in r and "gutschriften" not in r

    pdf = await client.get(f"/api/kundenportal/rechnungen/{gutschrift['id']}/pdf", headers=kopf)
    assert pdf.status_code == 200
    with pymupdf.open(stream=pdf.content, filetype="pdf") as dokument:
        text = " ".join(" ".join(seite.get_text() for seite in dokument).split())
    assert f"Bezug: Rechnung {original['rechnungsnummer']}" in text and "Grund: Kulanz Portal" in text


# --- Migration 0108 ------------------------------------------------------------------------


async def test_migration_0108_up_down_up(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    engine = _sync_engine()
    rechnung_id = uuid.uuid4()
    try:
        await _migrieren("downgrade", "0107")
        assert not {"rechnungsart", "angebot_id", "bezug_rechnung_id", "gutschrift_grund"} & set(
            _spalten(engine, "rechnungen")
        )
        assert not {"abschlag_rechnung_id", "bezug_position_id"} & set(_spalten(engine, "rechnung_positionen"))
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(
                text(
                    "INSERT INTO rechnungen (id, mandant_id, kunde_id, rechnungsnummer, betrag_netto, mwst_satz, "
                    "erstellt_von, ist_storno) VALUES (:id, :m, :k, 'R-MIG-0108', 0, 19, :u, true)"
                ),
                {"id": rechnung_id, "m": mandant.id, "k": kunde.id, "u": user.id},
            )

        await _migrieren("upgrade", "head")

        spalten = _spalten(engine, "rechnungen")
        assert spalten["rechnungsart"]["nullable"] is False
        assert {"angebot_id", "bezug_rechnung_id", "gutschrift_grund"} <= set(spalten)
        assert {"abschlag_rechnung_id", "bezug_position_id"} <= set(_spalten(engine, "rechnung_positionen"))
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            # Bestand (auch Storno-Belege) bleibt 'rechnung'.
            assert conn.execute(
                text("SELECT rechnungsart, ist_storno FROM rechnungen WHERE id = :id"), {"id": rechnung_id}
            ).one() == ("rechnung", True)
            with pytest.raises(Exception, match="ck_rechnungen_rechnungsart_valid"):
                conn.execute(text("UPDATE rechnungen SET rechnungsart = 'quatsch' WHERE id = :id"), {"id": rechnung_id})
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for tabelle in ("rechnungen", "rechnung_positionen"):
                relrls, relforce = conn.execute(
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": tabelle}
                ).one()
                assert relrls and relforce, tabelle
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
