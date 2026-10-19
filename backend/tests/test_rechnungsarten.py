"""Rechnungsarten (Migration 0108): Rechnung aus Angebot, Abschlag, Schlussrechnung
mit Anrechnung der Abschlaege, Gutschrift und die Offene-Posten-Regel."""
import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import mahnwesen_service, rechnung_service
from tests.conftest import auth_headers, login
from tests.test_steuer_je_position import _checks, _sync_engine, _spalten

_BACKEND = os.path.dirname(os.path.dirname(__file__))

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
