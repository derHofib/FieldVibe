"""Steuerkategorien Z, E und AE (Migration 0105, Schritt 3 des Rechnungsstrangs):
Gruende, 13b-Voraussetzungen, Versandpruefung, E-Rechnung, PDF und
Erloeskonten fuer DATEV/UStVA."""
import csv
import io
import uuid
from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from lxml import etree
from sqlalchemy import text

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import e_invoice_service, steuer_service
from tests.conftest import auth_headers, login
from tests.test_steuer_je_position import (
    _KU_HINWEIS,
    _admin,
    _checks,
    _migrieren,
    _spalten,
    _sync_engine,
)

_PV_HINWEIS = steuer_service.STEUER_GRUENDE["pv_12_3"][1]
_RC_HINWEIS = steuer_service.STEUER_GRUENDE["reverse_charge_13b"][1]
_E_TEXT = "Steuerfreie Lieferung nach § 4 Nr. 1 UStG"

_POS_S = {"beschreibung": "Material", "einzelpreis": "100"}
_POS_Z = {"beschreibung": "PV-Anlage", "einzelpreis": "200", "steuer_kategorie": "Z", "steuer_grund": "pv_12_3"}
_POS_AE = {
    "beschreibung": "Bauleistung",
    "einzelpreis": "300",
    "steuer_kategorie": "AE",
    "steuer_grund": "reverse_charge_13b",
}
_POS_E = {
    "beschreibung": "Ausfuhr",
    "einzelpreis": "40",
    "steuer_kategorie": "E",
    "steuer_grund": "sonstige_befreiung",
    "steuer_grund_text": _E_TEXT,
}

_MANDANT_MIT_UST = {"ust_idnr": "DE123456789", "steuernummer": "12/345/67890"}
_KUNDE_13B = {"typ": "gewerbe", "ust_idnr": "DE987654321", "ust_13b_nachweis_bis": date(2099, 12, 31)}
_E_RECHNUNG = {
    "e_rechnung_aktiv": True,
    "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
    "ust_idnr": "DE123456789",
}
_KUNDE_E_RECHNUNG = {
    **_KUNDE_13B,
    "adresse": {"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
}


async def _anlegen(client, token, kunde, positionen, **extra):
    return await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            "positionen": positionen,
            **extra,
        },
    )


async def _rechnung(client, token, kunde, positionen, **extra) -> dict:
    resp = await _anlegen(client, token, kunde, positionen, **extra)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _versenden(client, token, rechnung_id):
    return await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )


async def _position_patch(client, token, rechnung, index, body):
    return await client.patch(
        f"/api/rechnungen/{rechnung['id']}/positionen/{rechnung['positionen'][index]['id']}",
        headers=auth_headers(token),
        json=body,
    )


async def _admin13b(client, make_mandant, make_user, make_kunde, firmendaten=None, **kunde_kw):
    return await _admin(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten=_MANDANT_MIT_UST if firmendaten is None else firmendaten,
        **({**_KUNDE_13B, **kunde_kw}),
    )


def _norm(text_: str) -> str:
    return " ".join(text_.split())


# --- Migration 0105 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_0105_up_down_up_mit_backfill(make_mandant, make_user, make_kunde):
    ku_mandant = await make_mandant()
    normal_mandant = await make_mandant()
    ku_user = await make_user(mandant=ku_mandant, role="mandant_admin", password="pw-123456")
    normal_user = await make_user(mandant=normal_mandant, role="mandant_admin", password="pw-123456")
    ku_kunde = await make_kunde(mandant=ku_mandant)
    normal_kunde = await make_kunde(mandant=normal_mandant)
    engine = _sync_engine()
    faelle = [
        ("ku-e", ku_mandant, ku_user, ku_kunde, "E", "0.00"),
        ("ku-s", ku_mandant, ku_user, ku_kunde, "S", "19.00"),
        ("normal-e", normal_mandant, normal_user, normal_kunde, "E", "0.00"),
    ]
    try:
        await _migrieren("downgrade", "0104")
        assert not {"steuer_grund", "steuer_grund_text"} & set(_spalten(engine, "rechnung_positionen"))
        assert "ust_13b_nachweis_bis" not in _spalten(engine, "kunden")

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(
                text("UPDATE mandanten SET firmendaten = '{\"ist_kleinunternehmer\": true}'::jsonb WHERE id = :m"),
                {"m": ku_mandant.id},
            )
            for name, mandant, user, kunde, kategorie, satz in faelle:
                rechnung_id = uuid.uuid4()
                conn.execute(
                    text(
                        "INSERT INTO rechnungen (id, mandant_id, kunde_id, rechnungsnummer, betrag_netto, "
                        "mwst_satz, erstellt_von) VALUES (:id, :m, :k, :nr, 0, :satz, :u)"
                    ),
                    {"id": rechnung_id, "m": mandant.id, "k": kunde.id, "nr": f"R-0105-{name}", "satz": satz, "u": user.id},
                )
                conn.execute(
                    text(
                        "INSERT INTO rechnung_positionen (mandant_id, rechnung_id, position, beschreibung, "
                        "menge, einzelpreis, steuer_kategorie, steuer_satz) VALUES (:m, :r, 1, :n, 1, 10, :kat, :satz)"
                    ),
                    {"m": mandant.id, "r": rechnung_id, "n": name, "kat": kategorie, "satz": satz},
                )

        await _migrieren("upgrade", "head")

        spalten = _spalten(engine, "rechnung_positionen")
        assert spalten["steuer_grund"]["nullable"] and spalten["steuer_grund_text"]["nullable"]
        assert _spalten(engine, "kunden")["ust_13b_nachweis_bis"]["nullable"]
        assert {
            "ck_rechnung_positionen_steuer_grund_valid",
            "ck_rechnung_positionen_steuer_grund_text_laenge",
        } <= _checks(engine)
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            gruende = dict(
                conn.execute(
                    text("SELECT beschreibung, steuer_grund FROM rechnung_positionen WHERE beschreibung IN ('ku-e', 'ku-s', 'normal-e')")
                ).all()
            )
            # Nur E bei Kleinunternehmer-Mandanten bekommt den Grund; Altbestand E/0 sonst bleibt ohne.
            assert gruende == {"ku-e": "kleinunternehmer_19", "ku-s": None, "normal-e": None}
            relrls, relforce = conn.execute(
                text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'rechnung_positionen'")
            ).one()
            assert relrls and relforce
            # Die CHECK-Constraints lehnen unbekannte Gruende und zu lange Texte ab.
            with pytest.raises(Exception, match="steuer_grund_valid"):
                with conn.begin_nested():
                    conn.execute(text("UPDATE rechnung_positionen SET steuer_grund = 'erfunden'"))
            with pytest.raises(Exception, match="steuer_grund_text_laenge"):
                with conn.begin_nested():
                    conn.execute(
                        text("UPDATE rechnung_positionen SET steuer_grund_text = :t"), {"t": "x" * 201}
                    )

        # down/up/down: symmetrisch
        await _migrieren("downgrade", "0104")
        assert not {"steuer_grund", "steuer_grund_text"} & set(_spalten(engine, "rechnung_positionen"))
        assert "ust_13b_nachweis_bis" not in _spalten(engine, "kunden")
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


# --- Steuergruende anlegen und aendern ------------------------------------------------


@pytest.mark.asyncio
async def test_z_nur_mit_pv_grund(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_Z])
    z = rechnung["positionen"][1]
    assert (z["steuer_kategorie"], z["steuer_satz"], z["steuer_grund"], z["steuer_grund_text"]) == (
        "Z", "0.00", "pv_12_3", None
    )
    assert rechnung["steuergruppen"][1] == {
        "kategorie": "Z", "satz": "0.00", "netto": "200.00", "steuer": "0.00",
        "hinweis": _PV_HINWEIS, "hinweise": [_PV_HINWEIS],
    }
    # Brutto = 100 + 19 + 200 + 0
    assert rechnung["betrag_brutto"] == "319.00"

    for grund, text_ in (
        (None, None),
        ("sonstige_befreiung", "Irgendwas steuerfrei"),
        ("reverse_charge_13b", None),
    ):
        body = {**_POS_Z, "steuer_grund": grund, "steuer_grund_text": text_}
        body = {k: v for k, v in body.items() if v is not None}
        resp = await client.post(
            f"/api/rechnungen/{rechnung['id']}/positionen", headers=auth_headers(token), json=body
        )
        assert resp.status_code == 422, (grund, resp.text)
        assert "nur § 12 Abs. 3 UStG (Photovoltaik)" in resp.json()["detail"]

    # Satz != 0 und Text bei anderem Grund als sonstige_befreiung
    schlechter_satz = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=auth_headers(token),
        json={**_POS_Z, "steuer_satz": "7"},
    )
    assert schlechter_satz.status_code == 422
    text_bei_pv = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=auth_headers(token),
        json={**_POS_Z, "steuer_grund_text": "nicht erlaubt"},
    )
    assert text_bei_pv.status_code == 422
    assert "nur bei sonstige_befreiung" in text_bei_pv.json()["detail"]


@pytest.mark.asyncio
async def test_kategorie_ergibt_sich_aus_dem_grund(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [{"beschreibung": "PV", "einzelpreis": "10", "steuer_grund": "pv_12_3"}])
    assert rechnung["positionen"][0]["steuer_kategorie"] == "Z"


@pytest.mark.asyncio
async def test_e_braucht_sonstige_befreiung_mit_text(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_E])
    e = rechnung["positionen"][1]
    assert (e["steuer_kategorie"], e["steuer_grund"], e["steuer_grund_text"]) == ("E", "sonstige_befreiung", _E_TEXT)
    assert rechnung["steuergruppen"][1]["hinweis"] == _E_TEXT

    url = f"/api/rechnungen/{rechnung['id']}/positionen"

    async def versuche(**felder):
        return await client.post(url, headers=auth_headers(token), json={**_POS_E, **felder})

    ohne_text = await client.post(
        url, headers=auth_headers(token),
        json={k: v for k, v in _POS_E.items() if k != "steuer_grund_text"},
    )
    assert ohne_text.status_code == 422
    assert "3 bis 200 Zeichen" in ohne_text.json()["detail"]
    assert (await versuche(steuer_grund_text="ab")).status_code == 422
    assert (await versuche(steuer_grund_text="   ")).status_code == 422
    assert (await versuche(steuer_grund_text="abc")).status_code == 200
    assert (await versuche(steuer_grund_text="x" * 200)).status_code == 200
    assert (await versuche(steuer_grund_text="x" * 201)).status_code == 422  # Schema (max_length)

    ohne_grund = await client.post(
        url, headers=auth_headers(token), json={"beschreibung": "x", "einzelpreis": "1", "steuer_kategorie": "E"}
    )
    assert ohne_grund.status_code == 422
    assert "braucht einen Steuergrund" in ohne_grund.json()["detail"]
    falscher_grund = await versuche(steuer_grund="pv_12_3", steuer_grund_text=None)
    assert falscher_grund.status_code == 422
    assert "passt nicht zur Steuerkategorie E" in falscher_grund.json()["detail"]
    ku_grund = await versuche(steuer_grund="kleinunternehmer_19", steuer_grund_text=None)
    assert ku_grund.status_code == 422
    assert "nur für Kleinunternehmer" in ku_grund.json()["detail"]


@pytest.mark.asyncio
async def test_s_mit_grund_und_ae_mit_falschem_grund_422(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S])
    url = f"/api/rechnungen/{rechnung['id']}/positionen"
    s_mit_grund = await client.post(url, headers=auth_headers(token), json={**_POS_S, "steuer_kategorie": "S", "steuer_grund": "pv_12_3"})
    assert s_mit_grund.status_code == 422
    assert "kein Steuergrund vorgesehen" in s_mit_grund.json()["detail"]
    ae_falsch = await client.post(url, headers=auth_headers(token), json={**_POS_AE, "steuer_grund": "pv_12_3"})
    assert ae_falsch.status_code == 422
    assert "reverse_charge_13b" in ae_falsch.json()["detail"]
    ae_ohne = await client.post(url, headers=auth_headers(token), json={k: v for k, v in _POS_AE.items() if k != "steuer_grund"})
    assert ae_ohne.status_code == 422
    ae_satz = await client.post(url, headers=auth_headers(token), json={**_POS_AE, "steuer_satz": "19"})
    assert ae_satz.status_code == 422


@pytest.mark.asyncio
async def test_position_patch_grund_und_kategoriewechsel(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S])

    ohne_grund = await _position_patch(client, token, rechnung, 0, {"steuer_kategorie": "Z"})
    assert ohne_grund.status_code == 422
    nur_satz_null = await _position_patch(client, token, rechnung, 0, {"steuer_satz": "0"})
    assert nur_satz_null.status_code == 422  # S/0 ist nicht zulaessig

    z = await _position_patch(client, token, rechnung, 0, {"steuer_kategorie": "Z", "steuer_grund": "pv_12_3"})
    assert z.status_code == 200, z.text
    pos = z.json()["positionen"][0]
    assert (pos["steuer_kategorie"], pos["steuer_satz"], pos["steuer_grund"]) == ("Z", "0.00", "pv_12_3")

    # Grund allein bestimmt die Kategorie; Text gehoert zum Grund und faellt beim Wechsel weg.
    e = await _position_patch(
        client, token, rechnung, 0, {"steuer_grund": "sonstige_befreiung", "steuer_grund_text": _E_TEXT}
    )
    assert e.status_code == 200, e.text
    assert e.json()["positionen"][0]["steuer_grund_text"] == _E_TEXT
    neuer_text = await _position_patch(client, token, rechnung, 0, {"steuer_grund_text": "Anderer Befreiungstext"})
    assert neuer_text.json()["positionen"][0]["steuer_grund_text"] == "Anderer Befreiungstext"

    zurueck = await _position_patch(client, token, rechnung, 0, {"steuer_kategorie": "S", "steuer_satz": "19"})
    assert zurueck.status_code == 200
    pos = zurueck.json()["positionen"][0]
    assert (pos["steuer_kategorie"], pos["steuer_satz"], pos["steuer_grund"], pos["steuer_grund_text"]) == (
        "S", "19.00", None, None
    )

    # Unveraenderte Beschreibung/Preis laesst den Grund unangetastet
    await _position_patch(client, token, rechnung, 0, {"steuer_kategorie": "Z", "steuer_grund": "pv_12_3"})
    preis = await _position_patch(client, token, rechnung, 0, {"einzelpreis": "55"})
    assert preis.json()["positionen"][0]["steuer_grund"] == "pv_12_3"


@pytest.mark.asyncio
async def test_kleinunternehmer_erzwingt_e_mit_grund(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_Z, _POS_AE])
    for p in rechnung["positionen"]:
        assert (p["steuer_kategorie"], p["steuer_satz"], p["steuer_grund"], p["steuer_grund_text"]) == (
            "E", "0.00", "kleinunternehmer_19", None
        )
    assert rechnung["steuergruppen"][0]["hinweis"] == _KU_HINWEIS

    nachtrag = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen", headers=auth_headers(token), json=_POS_E
    )
    assert nachtrag.status_code == 200
    assert nachtrag.json()["positionen"][-1]["steuer_grund"] == "kleinunternehmer_19"
    patch = await _position_patch(client, token, rechnung, 0, {"steuer_kategorie": "S", "steuer_satz": "19"})
    assert patch.json()["positionen"][0]["steuer_kategorie"] == "E"

    # Kein 13b-Check beim Kleinunternehmer (Kunde ohne USt-IdNr.), Versand ohne Steuerpruefung
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 200, versand.text
    assert versand.json()["betrag_brutto"] == versand.json()["betrag_netto"]


# --- 13b-Voraussetzungen -------------------------------------------------------------


@pytest.mark.asyncio
async def test_ae_voraussetzungen_beim_anlegen(client, make_mandant, make_user, make_kunde):
    # ohne USt-IdNr. beim Kunden
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_idnr=None)
    resp = await _anlegen(client, token, kunde, [_POS_AE])
    assert resp.status_code == 422
    assert "USt-IdNr." in resp.json()["detail"]
    assert "§ 13b" in resp.json()["detail"]

    # ohne Nachweis
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_13b_nachweis_bis=None)
    resp = await _anlegen(client, token, kunde, [_POS_AE])
    assert resp.status_code == 422
    assert "Ablaufdatum der Bescheinigung USt 1 TG" in resp.json()["detail"]

    # abgelaufen vor dem Leistungsdatum (10.08.2026)
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_13b_nachweis_bis=date(2026, 8, 9))
    resp = await _anlegen(client, token, kunde, [_POS_AE])
    assert resp.status_code == 422
    assert "am 09.08.2026 abgelaufen" in resp.json()["detail"]
    assert "Leistungsdatum 10.08.2026" in resp.json()["detail"]
    # Es wurde keine Rechnung angelegt (Rollback), auch keine Nummer verbraucht.
    liste = await client.get("/api/rechnungen", headers=auth_headers(token))
    assert liste.json()["gesamt_anzahl"] == 0

    # am Leistungstag gueltig (Stichtag eingeschlossen)
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_13b_nachweis_bis=date(2026, 8, 10))
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_AE])
    assert rechnung["steuergruppen"][1]["kategorie"] == "AE"
    assert rechnung["steuergruppen"][1]["hinweis"] == _RC_HINWEIS


@pytest.mark.asyncio
async def test_ae_voraussetzungen_ohne_leistungsdatum_gilt_heute(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_13b_nachweis_bis=date(2020, 1, 1))
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "positionen": [_POS_AE]},
    )
    assert resp.status_code == 422
    assert "abgelaufen (heute," in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ae_voraussetzungen_bei_nachtraeglicher_position_und_patch(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde, ust_idnr=None)
    rechnung = await _rechnung(client, token, kunde, [_POS_S])
    neu = await client.post(f"/api/rechnungen/{rechnung['id']}/positionen", headers=auth_headers(token), json=_POS_AE)
    assert neu.status_code == 422
    patch = await _position_patch(
        client, token, rechnung, 0, {"steuer_kategorie": "AE", "steuer_grund": "reverse_charge_13b"}
    )
    assert patch.status_code == 422
    assert "USt-IdNr." in patch.json()["detail"]
    nachher = await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))
    assert nachher.json()["positionen"][0]["steuer_kategorie"] == "S"

    # Kundendaten ergaenzen -> jetzt klappt es
    kunde_patch = await client.patch(
        f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"ust_idnr": "DE111222333"}
    )
    assert kunde_patch.status_code == 200
    assert kunde_patch.json()["ust_13b_nachweis_bis"] == "2099-12-31"
    ok = await _position_patch(
        client, token, rechnung, 0, {"steuer_kategorie": "AE", "steuer_grund": "reverse_charge_13b"}
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_kunde_api_nachweis_anlegen_aendern_lesen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    angelegt = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Bau GmbH", "typ": "gewerbe", "ust_idnr": "DE111222333", "ust_13b_nachweis_bis": "2027-05-31"},
    )
    assert angelegt.status_code == 201
    assert angelegt.json()["ust_13b_nachweis_bis"] == "2027-05-31"
    kunde_id = angelegt.json()["id"]
    geaendert = await client.patch(
        f"/api/kunden/{kunde_id}", headers=auth_headers(token), json={"ust_13b_nachweis_bis": "2028-01-31"}
    )
    assert geaendert.json()["ust_13b_nachweis_bis"] == "2028-01-31"
    geleert = await client.patch(
        f"/api/kunden/{kunde_id}", headers=auth_headers(token), json={"ust_13b_nachweis_bis": None}
    )
    assert geleert.json()["ust_13b_nachweis_bis"] is None
    assert (await client.get(f"/api/kunden/{kunde_id}", headers=auth_headers(token))).json()["ust_idnr"] == "DE111222333"


# --- Versandpruefung -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_versand_ae_pruefung_wiederholt_sich(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_AE])

    # Der Nachweis laeuft nach dem Anlegen ab -> Versand scheitert
    await client.patch(f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"ust_13b_nachweis_bis": "2026-08-01"})
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert versand.json()["detail"].startswith("Rechnung kann nicht versendet werden:")
    assert "am 01.08.2026 abgelaufen" in versand.json()["detail"]
    assert (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()["status"] == "entwurf"

    # USt-IdNr. des Kunden entfernt
    await client.patch(
        f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"ust_13b_nachweis_bis": "2099-01-01", "ust_idnr": None}
    )
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert steuer_service.MELDUNG_KUNDE_UST_IDNR_13B in versand.json()["detail"]

    # alles in Ordnung
    await client.patch(f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"ust_idnr": "DE987654321"})
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 200, versand.text
    assert versand.json()["status"] == "versendet"

    # Storno bleibt moeglich, auch wenn der Nachweis inzwischen abgelaufen ist
    await client.patch(f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"ust_13b_nachweis_bis": "2026-08-01"})
    storno = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=auth_headers(token))
    assert storno.status_code == 201
    assert storno.json()["positionen"][1]["steuer_grund"] == "reverse_charge_13b"
    assert storno.json()["steuergruppen"][1]["netto"] == "-300.00"


@pytest.mark.asyncio
async def test_versand_ae_ohne_eigene_ust_idnr_422(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(
        client, make_mandant, make_user, make_kunde, firmendaten={"steuernummer": "12/345/67890"}
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_AE])
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert steuer_service.MELDUNG_MANDANT_UST_IDNR_13B in versand.json()["detail"]

    await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": {"ust_idnr": "DE123456789"}}
    )
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200


@pytest.mark.asyncio
async def test_versand_e_null_ohne_grund_nicht_kleinunternehmer(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    # Beleg mit Satz 0: Positionen erben E/0 ohne Grund (Altverhalten, im Entwurf zulaessig)
    rechnung = await _rechnung(
        client, token, kunde,
        [{"beschreibung": "a", "einzelpreis": "10"}, {"beschreibung": "b", "einzelpreis": "20"}],
        mwst_satz="0.00",
    )
    assert [(p["steuer_kategorie"], p["steuer_grund"]) for p in rechnung["positionen"]] == [("E", None), ("E", None)]

    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    detail = versand.json()["detail"]
    assert "Position 1" in detail and "Position 2" in detail
    assert "braucht einen Steuergrund" in detail
    assert (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()["status"] == "entwurf"

    for index in (0, 1):
        r = await _position_patch(
            client, token, rechnung, index, {"steuer_grund": "sonstige_befreiung", "steuer_grund_text": _E_TEXT}
        )
        assert r.status_code == 200, r.text
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200


@pytest.mark.asyncio
async def test_versand_rechnung_ohne_positionen_mit_satz_null_nicht_kleinunternehmer(
    client, make_mandant, make_user, make_kunde
):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [], betrag_netto="100", mwst_satz="0.00")
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert "Steuergrund" in versand.json()["detail"]
    # Mit 19 % unveraendert versendbar
    normal = await _rechnung(client, token, kunde, [], betrag_netto="100")
    assert (await _versenden(client, token, normal["id"])).status_code == 200


@pytest.mark.asyncio
async def test_versand_kleinunternehmer_unveraendert(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _rechnung(client, token, kunde, [], betrag_netto="100")
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200


@pytest.mark.asyncio
async def test_versendete_rechnung_steuergrund_unveraenderlich(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_Z, _POS_AE])
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200
    gesperrt = await _position_patch(client, token, rechnung, 0, {"steuer_grund": "sonstige_befreiung", "steuer_grund_text": "abc"})
    assert gesperrt.status_code == 400
    neu = await client.post(f"/api/rechnungen/{rechnung['id']}/positionen", headers=auth_headers(token), json=_POS_Z)
    assert neu.status_code == 400
    nachher = await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))
    assert nachher.json()["positionen"][0]["steuer_grund"] == "pv_12_3"


# --- Belegkopf -----------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("satz,erwartet", [("5", 422), ("19", 201), ("19.00", 201), ("7", 201), ("0", 201), ("0.00", 201), ("16", 422), ("-1", 422)])
async def test_belegkopf_mwst_satz_nur_19_7_0(client, make_mandant, make_user, make_kunde, satz, erwartet):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    resp = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "mwst_satz": satz}
    )
    assert resp.status_code == erwartet, resp.text
    if erwartet == 422:
        assert "mwst_satz muss 19, 7 oder 0 sein" in resp.text


# --- E-Rechnung ----------------------------------------------------------------------

_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"


def _steuerbloecke(xml: bytes) -> list[dict]:
    wurzel = etree.fromstring(xml)
    bloecke = wurzel.xpath("//*[local-name()='ApplicableHeaderTradeSettlement']/*[local-name()='ApplicableTradeTax']")
    ergebnis = []
    for block in bloecke:
        def feld(name):
            gefunden = block.xpath(f"*[local-name()='{name}']")
            return gefunden[0].text if gefunden else None
        ergebnis.append(
            {"kategorie": feld("CategoryCode"), "satz": feld("RateApplicablePercent"), "grund": feld("ExemptionReason"), "basis": feld("BasisAmount")}
        )
    return ergebnis


@pytest.mark.asyncio
async def test_e_rechnung_xml_je_gruppe_mit_kategorie_und_grund(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG, **_KUNDE_E_RECHNUNG
    )
    zweiter_text = "Steuerfreie Leistung nach § 4 Nr. 8 UStG"
    rechnung = await _rechnung(
        client, token, kunde,
        [
            _POS_S,
            _POS_Z,
            _POS_AE,
            _POS_E,
            {**_POS_E, "steuer_grund_text": zweiter_text, "einzelpreis": "10"},
        ],
    )
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 200, versand.text
    assert versand.json()["xml_object_key"] is not None
    xml = (await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))).content

    bloecke = {b["kategorie"]: b for b in _steuerbloecke(xml)}
    assert set(bloecke) == {"S", "Z", "E", "AE"}
    assert bloecke["S"]["satz"] == "19.00" and bloecke["S"]["grund"] is None
    # BR-Z-10: Z traegt keinen Befreiungsgrund, der Hinweis steht als Rechnungsvermerk.
    assert bloecke["Z"]["satz"] == "0.00" and bloecke["Z"]["grund"] is None
    assert _PV_HINWEIS.encode() in xml
    assert bloecke["AE"]["satz"] == "0.00" and bloecke["AE"]["grund"] == _RC_HINWEIS
    # Eine Gruppe (E, 0 %) mit zwei Gruenden: Texte werden zusammengefuehrt, Betrag bleibt eine Gruppe.
    assert bloecke["E"]["grund"] == f"{_E_TEXT}; {zweiter_text}"
    assert bloecke["E"]["basis"] == "50.00"

    # BT-31 und BT-48 (Verkaeufer-/Kaeufer-USt-IdNr., Schema "VA")
    registrierungen = etree.fromstring(xml).xpath("//*[local-name()='SpecifiedTaxRegistration']/*[local-name()='ID']")
    assert {(r.get("schemeID"), r.text) for r in registrierungen} == {("VA", "DE123456789"), ("VA", "DE987654321")}

    # Zeilenebene: Nicht-Kleinunternehmer-E wird als E ausgegeben (frueher S/0)
    zeilen = etree.fromstring(xml).xpath(
        "//*[local-name()='IncludedSupplyChainTradeLineItem']//*[local-name()='ApplicableTradeTax']/*[local-name()='CategoryCode']"
    )
    assert [z.text for z in zeilen] == ["S", "Z", "AE", "E", "E"]


@pytest.mark.asyncio
async def test_e_rechnung_pflichtangaben_fehlen_versand_422_ohne_stillen_fallback(
    client, make_mandant, make_user, make_kunde
):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG,
        typ="gewerbe", adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S])
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert "USt-IdNr. des Kunden fehlt" in versand.json()["detail"]
    nachher = (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()
    assert nachher["status"] == "entwurf" and nachher["versendet_am"] is None


def test_e_rechnung_ae_braucht_beide_ust_idnrn():
    mandant = Mandant(name="Bau", firmendaten={**_E_RECHNUNG, "ust_idnr": None, "steuernummer": "12/345/67890"})
    kunde = Kunde(name="K", typ="privat", adresse={"strasse": "a", "plz": "1", "ort": "b"}, ust_idnr=None)
    rechnung = Rechnung(rechnungsnummer="R-1", leistungsdatum=date(2026, 8, 10), betrag_netto=Decimal("0"), mwst_satz=Decimal("19"))
    position = RechnungPosition(position=1, beschreibung="x", menge=Decimal(1), einzelpreis=Decimal(10), steuer_kategorie="AE", steuer_satz=Decimal(0))
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(mandant, rechnung, kunde, [position])
    assert steuer_service.MELDUNG_MANDANT_UST_IDNR_13B in probleme
    assert steuer_service.MELDUNG_KUNDE_UST_IDNR_13B in probleme
    # Ohne AE-Position bleibt das beim privaten Kunden ohne Fehlermeldung
    position.steuer_kategorie = "S"
    position.steuer_satz = Decimal("19")
    assert steuer_service.MELDUNG_KUNDE_UST_IDNR_13B not in e_invoice_service.pruefe_en16931_vollstaendigkeit(
        mandant, rechnung, kunde, [position]
    )


@pytest.mark.asyncio
async def test_e_rechnung_xsd_fehler_wird_422_statt_500(client, make_mandant, make_user, make_kunde, monkeypatch):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG, **_KUNDE_E_RECHNUNG
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S])

    original = e_invoice_service.cii_xml_bytes
    zustand = {"kaputt": True}

    def kaputt(dokument):
        if zustand["kaputt"]:
            raise etree.DocumentInvalid("Element '{urn:geheim}ID': interne Details")
        return original(dokument)

    monkeypatch.setattr(e_invoice_service, "cii_xml_bytes", kaputt)
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert versand.json()["detail"] == "E-Rechnung konnte nicht erzeugt werden: Schema-Validierung fehlgeschlagen"
    assert "geheim" not in versand.text
    nachher = (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()
    assert nachher["status"] == "entwurf" and nachher["xml_object_key"] is None

    zustand["kaputt"] = False
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200


@pytest.mark.asyncio
async def test_e_rechnung_unerwarteter_fehler_beim_xml_aufbau_ebenfalls_422(
    client, make_mandant, make_user, make_kunde, monkeypatch
):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG, **_KUNDE_E_RECHNUNG
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S])

    def kaputt(*_args, **_kwargs):
        raise ValueError("irgendwas")

    monkeypatch.setattr(e_invoice_service, "baue_cii_dokument", kaputt)
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 422
    assert versand.json()["detail"].startswith("E-Rechnung konnte nicht erzeugt werden:")


@pytest.mark.asyncio
async def test_storno_mit_e_rechnung_blockiert_nicht_bei_xml_fehler(
    client, make_mandant, make_user, make_kunde, monkeypatch
):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=_E_RECHNUNG, **_KUNDE_E_RECHNUNG
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S])
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200

    def kaputt(_dokument):
        raise etree.DocumentInvalid("x")

    monkeypatch.setattr(e_invoice_service, "cii_xml_bytes", kaputt)
    storno = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=auth_headers(token))
    assert storno.status_code == 201
    assert storno.json()["xml_object_key"] is None


# --- PDF -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_enthaelt_hinweise_und_reverse_charge_vermerk(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_Z, _POS_AE, _POS_E])
    assert (await _versenden(client, token, rechnung["id"])).status_code == 200
    pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    dokument = pymupdf.open(stream=pdf.content)
    text_ = _norm("\n".join(seite.get_text() for seite in dokument))
    assert _norm(_PV_HINWEIS) in text_
    assert _norm(_RC_HINWEIS) in text_
    assert "Steuerschuldner ist der Leistungsempfänger" in text_
    assert _norm(_E_TEXT) in text_
    assert "USt. 0 % (Reverse Charge)" in text_
    assert "USt. 0 % (steuerfrei)" in text_
    assert "zzgl. 19 % USt." in text_
    # Kaeufer-USt-IdNr. im Kopfbereich
    assert "DE987654321" in text_
    # Brutto: 100 + 19 + 200 + 300 + 40
    assert "659,00 €" in text_


# --- Erloeskonten, UStVA und DATEV ---------------------------------------------------

_KONTEN = {
    "buchhaltung": {
        "erloeskonten": {
            "Z:0.00": {"konto": "8101", "bu": "11"},
            "E:0.00": {"konto": "8102", "bu": ""},
            "AE:0.00": {"konto": "8103", "bu": "12"},
        }
    }
}


async def _gemischt_versendet(client, token, kunde) -> None:
    rechnung = await _rechnung(
        client, token, kunde, [_POS_S, {**_POS_S, "einzelpreis": "50", "steuer_satz": "7"}, _POS_Z, _POS_AE, _POS_E]
    )
    versand = await _versenden(client, token, rechnung["id"])
    assert versand.status_code == 200, versand.text


def _datev_zeilen(antwort):
    return list(csv.reader(io.StringIO(antwort.text), delimiter=";"))[2:]


@pytest.mark.asyncio
async def test_datev_konten_je_gruppe_aus_konfiguration(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    await _gemischt_versendet(client, token, kunde)
    ohne = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert ohne.status_code == 422
    assert "Für Steuerkategorie Z ist kein Erlöskonto hinterlegt – bitte unter Firmendaten ➝ Buchhaltung eintragen" in ohne.json()["detail"]
    assert "Z:0.00" in ohne.json()["detail"]

    teil = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"buchhaltung": {"erloeskonten": {"Z:0.00": {"konto": "8101", "bu": "11"}}}}},
    )
    assert teil.status_code == 200
    noch_ohne = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert noch_ohne.status_code == 422
    assert "Steuerkategorie E ist kein Erlöskonto" in noch_ohne.json()["detail"]

    voll = await client.patch("/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": _KONTEN})
    assert voll.status_code == 200
    # Andere Firmendaten bleiben erhalten
    assert voll.json()["firmendaten"]["ust_idnr"] == "DE123456789"
    export = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert export.status_code == 200
    # Defaults S/19 und S/7 unveraendert, Z/E/AE aus der Konfiguration (Reihenfolge S, Z, E, AE)
    assert [(z[0], z[4], z[5]) for z in _datev_zeilen(export)] == [
        ("119,00", "8400", "3"),
        ("53,50", "8300", "2"),
        ("200,00", "8101", "11"),
        ("40,00", "8102", ""),
        ("300,00", "8103", "12"),
    ]


@pytest.mark.asyncio
async def test_datev_ohne_nullsteuer_belege_braucht_keine_konfiguration(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_S])
    await _versenden(client, token, rechnung["id"])
    export = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert export.status_code == 200
    assert [(z[0], z[4], z[5]) for z in _datev_zeilen(export)] == [("119,00", "8400", "3")]


@pytest.mark.asyncio
async def test_datev_kleinunternehmer_default_und_konfiguration(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_Z])
    await _versenden(client, token, rechnung["id"])
    export = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert export.status_code == 200
    assert [(z[0], z[4], z[5]) for z in _datev_zeilen(export)] == [("300,00", "8400", "")]

    # Ein hinterlegter Eintrag gewinnt auch beim Kleinunternehmer
    await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"buchhaltung": {"erloeskonten": {"E:0.00": {"konto": "8195", "bu": ""}}}}},
    )
    export = await client.get("/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert [(z[4]) for z in _datev_zeilen(export)] == ["8195"]


@pytest.mark.asyncio
async def test_ust_va_sonstige_umsaetze_und_zahllast_unveraendert(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    await _gemischt_versendet(client, token, kunde)
    # Ohne Konten-Konfiguration funktioniert die UStVA (sie braucht keine Konten)
    ustva = await client.get("/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert ustva.status_code == 200, ustva.text
    bericht = ustva.json()
    assert {z["satz"]: (z["netto"], z["steuer"]) for z in bericht["umsatzsteuer_saetze"]} == {
        "19.00": ("100.00", "19.00"),
        "7.00": ("50.00", "3.50"),
    }
    assert bericht["sonstige_umsaetze"] == [
        {"kategorie": "AE", "bezeichnung": "Steuerpflichtige Umsätze, Steuerschuldner ist der Leistungsempfänger (§ 13b)", "netto": "300.00", "kennzahl": None},
        {"kategorie": "Z", "bezeichnung": "Umsätze zum Steuersatz 0 % (§ 12 Abs. 3)", "netto": "200.00", "kennzahl": None},
        {"kategorie": "E", "bezeichnung": "Sonstige steuerfreie Umsätze", "netto": "40.00", "kennzahl": None},
    ]
    assert bericht["summe_umsatzsteuer"] == "22.50"
    assert bericht["zahllast"] == "22.50"


@pytest.mark.asyncio
async def test_ust_va_storno_hebt_sonstige_umsaetze_auf(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    rechnung = await _rechnung(client, token, kunde, [_POS_AE])
    await _versenden(client, token, rechnung["id"])
    await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=auth_headers(token))
    bericht = (
        await client.get("/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    ).json()
    assert [(z["kategorie"], z["netto"]) for z in bericht["sonstige_umsaetze"]] == [("AE", "0.00")]


@pytest.mark.asyncio
async def test_kleinunternehmer_ust_va_ohne_sonstige_umsaetze(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _rechnung(client, token, kunde, [_POS_S, _POS_S])
    await _versenden(client, token, rechnung["id"])
    bericht = (
        await client.get("/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    ).json()
    assert bericht["umsatzsteuer_saetze"] == [{"satz": "0.00", "netto": "200.00", "steuer": "0.00"}]
    assert bericht["sonstige_umsaetze"] == []
    assert bericht["zahllast"] == "0.00"


# --- Konfigurations-Validierung ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erloeskonten",
    [
        {"X:0.00": {"konto": "8400", "bu": ""}},
        {"S:5.00": {"konto": "8400", "bu": ""}},
        {"Z:0.00": {"konto": "840", "bu": ""}},
        {"Z:0.00": {"konto": "840000000", "bu": ""}},
        {"Z:0.00": {"konto": "84a0", "bu": ""}},
        {"Z:0.00": {"bu": "3"}},
        {"Z:0.00": {"konto": "8400", "bu": "1234"}},
        {"Z:0.00": {"konto": "8400", "bu": "a"}},
        {"Z:0.00": {"konto": "8400", "extra": "x"}},
        {"Z:0.00": "8400"},
    ],
)
async def test_buchhaltung_validierung_422(client, make_mandant, make_user, erloeskonten):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"buchhaltung": {"erloeskonten": erloeskonten}}},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_buchhaltung_speichern_erhaelt_andere_firmendaten(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kopf = auth_headers(token)
    await client.patch("/api/mandant/einstellungen", headers=kopf, json={"firmendaten": {"iban": "DE00", "ust_idnr": "DE1"}})
    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=kopf,
        json={"firmendaten": {"buchhaltung": {"erloeskonten": {"S:19.00": {"konto": " 8401 ", "bu": None}, "AE:0.00": {"konto": "8337", "bu": "94"}}}}},
    )
    assert resp.status_code == 200, resp.text
    fd = resp.json()["firmendaten"]
    assert fd["iban"] == "DE00" and fd["ust_idnr"] == "DE1"
    assert fd["buchhaltung"]["erloeskonten"] == {
        "S:19.00": {"konto": "8401", "bu": ""},
        "AE:0.00": {"konto": "8337", "bu": "94"},
    }
    # Ein anderes Formular speichert nur seinen Ausschnitt -- die Konten bleiben
    spaeter = await client.patch("/api/mandant/einstellungen", headers=kopf, json={"firmendaten": {"iban": "DE11"}})
    assert spaeter.json()["firmendaten"]["buchhaltung"]["erloeskonten"]["AE:0.00"]["konto"] == "8337"
    # S/19 aus der Konfiguration ueberschreibt den Default
    assert spaeter.json()["firmendaten"]["iban"] == "DE11"


# --- Berechnungskern ----------------------------------------------------------------


def _pos(menge, preis, kategorie, satz, grund=None, text=None) -> RechnungPosition:
    return RechnungPosition(
        menge=Decimal(str(menge)), einzelpreis=Decimal(str(preis)), steuer_kategorie=kategorie,
        steuer_satz=Decimal(str(satz)), steuer_grund=grund, steuer_grund_text=text,
    )


def test_gruppen_trennen_nicht_nach_grund_summen_bleiben():
    beleg = Rechnung(betrag_netto=Decimal("0"), mwst_satz=Decimal("19"))
    # Zwei verschiedene Gruende in einer (E, 0)-Gruppe: 0,004 + 0,004 rundet gruppenweise auf 0,01
    positionen = [
        _pos(1, "0.004", "E", 0, "sonstige_befreiung", "Erster Befreiungstext"),
        _pos(1, "0.004", "E", 0, "sonstige_befreiung", "Zweiter Befreiungstext"),
        _pos(1, "0.004", "E", 0, "sonstige_befreiung", "Erster Befreiungstext"),
    ]
    gruppen = steuer_service.steuer_gruppen(beleg, positionen)
    assert len(gruppen) == 1
    assert gruppen[0].netto == Decimal("0.01")
    assert gruppen[0].hinweise == ("Erster Befreiungstext", "Zweiter Befreiungstext")
    assert gruppen[0].hinweis == "Erster Befreiungstext; Zweiter Befreiungstext"
    assert gruppen[0].gruende == ("sonstige_befreiung",)


def test_hinweistext_aus_katalog():
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "Z", 0, "pv_12_3")) == _PV_HINWEIS
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "AE", 0, "reverse_charge_13b")) == _RC_HINWEIS
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "E", 0, "kleinunternehmer_19")) == _KU_HINWEIS
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "E", 0, "sonstige_befreiung", " Text ")) == "Text"
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "E", 0, "sonstige_befreiung")) is None
    assert steuer_service.steuer_hinweis_text(_pos(1, 1, "S", 19)) is None


@pytest.mark.asyncio
async def test_sql_summen_unveraendert_durch_gruende(client, make_mandant, make_user, make_kunde):
    # Uebersicht (SQL) und Detail (Python) bleiben mit gemischten Gruenden identisch.
    token, kunde = await _admin13b(client, make_mandant, make_user, make_kunde)
    detail = await _rechnung(client, token, kunde, [_POS_S, _POS_Z, _POS_AE, _POS_E, {**_POS_E, "steuer_grund_text": "Anderer Text"}])
    liste = (await client.get("/api/rechnungen", headers=auth_headers(token))).json()
    eintrag = liste["eintraege"][0]
    assert eintrag["betrag_brutto"] == detail["betrag_brutto"] == "699.00"
    assert liste["summe_netto"] == detail["betrag_netto"] == "680.00"
    assert liste["summe_brutto"] == "699.00"
