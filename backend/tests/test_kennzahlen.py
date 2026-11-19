from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung
from app.models.telefonat import Telefonat
from tests.conftest import auth_headers, login

KATALOG = "/api/kennzahlen/katalog"
DATEN = "/api/kennzahlen/daten"
DASHBOARDS = "/api/kennzahlen/dashboards"


def _utc(jahr, monat, tag, stunde=12):
    return datetime(jahr, monat, tag, stunde, tzinfo=timezone.utc)


def _naiv(jahr, monat, tag, stunde=12):
    # created_at ist im ORM ohne timezone=True gemappt (siehe test_statistik_aggregat.py).
    return datetime(jahr, monat, tag, stunde)


async def _kopf(client, make_mandant, make_user, mandant=None, role="mandant_admin", name="Test User"):
    mandant = mandant or await make_mandant()
    user = await make_user(mandant=mandant, role=role, password="pw-123456", name=name)
    return mandant, user, auth_headers(await login(client, user.email, "pw-123456"))


def _p(kennzahl, **kw):
    basis = {"kennzahl": kennzahl, "von": "2026-01-01", "bis": "2026-03-31"}
    basis.update(kw)
    return basis


def _layout(anzahl=1):
    return {
        "zeitraum": "monat",
        "widgets": [
            {"id": f"w{i}", "kennzahl": "vorgaenge.offen", "darstellung": "zahl", "groesse": "s"}
            for i in range(anzahl)
        ],
    }


# --- Katalog ---------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_katalog_admin_sieht_alle(client, make_mandant, make_user):
    _, _, h = await _kopf(client, make_mandant, make_user)
    resp = await client.get(KATALOG, headers=h)
    assert resp.status_code == 200
    schluessel = [k["schluessel"] for k in resp.json()]
    assert schluessel[:3] == ["vorgaenge.erstellt", "vorgaenge.abgeschlossen", "vorgaenge.durchlaufzeit"]
    assert len(schluessel) == 15
    assert {"finanzen.umsatz_netto", "sales.angebotsquote", "telefonate.dauer"} <= set(schluessel)
    erstellt = resp.json()[0]
    assert erstellt["art"] == "zeitraum" and erstellt["summierbar"] is True and erstellt["bereich"] == "vorgaenge"
    assert {"schluessel": "monat", "label": "Monat", "zeit": True} in erstellt["gruppierungen"]


@pytest.mark.asyncio
async def test_katalog_ohne_abrechnung_keine_finanzen_und_sales(client, make_mandant, make_user):
    # "mitarbeiter" hat statistik.sehen, aber kein abrechnung.sehen
    _, _, h = await _kopf(client, make_mandant, make_user, role="mitarbeiter")
    schluessel = [k["schluessel"] for k in (await client.get(KATALOG, headers=h)).json()]
    assert schluessel
    assert not [s for s in schluessel if s.startswith(("finanzen.", "sales."))]
    assert "vorgaenge.offen" in schluessel and "telefonate.anzahl" in schluessel


@pytest.mark.asyncio
async def test_ohne_statistik_recht_403(client, make_mandant, make_user):
    mandant = await make_mandant()
    # Account-Typ "Mitarbeiter" ohne statistik.sehen: Recht entziehen
    user = await make_user(mandant=mandant, role="mitarbeiter", password="pw-123456")
    from sqlalchemy import update
    from app.models.account_typ import AccountTypRecht
    async with system_session(grund="test") as s:
        await s.execute(
            update(AccountTypRecht)
            .where(AccountTypRecht.account_typ_id == user.account_typ_id, AccountTypRecht.bereich == "statistik")
            .values(erlaubt=False)
        )
    h = auth_headers(await login(client, user.email, "pw-123456"))
    assert (await client.get(KATALOG, headers=h)).status_code == 403
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.offen"))).status_code == 403
    assert (await client.get(DASHBOARDS, headers=h)).status_code == 403


# --- Daten -----------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zeitreihe_lueckenlos_mit_vorperiode(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    # Zeitraum Jan-Mrz: Jan 2, Mrz 1 (Feb leer); Vergleich Okt-Dez 2025: Okt 1, Nov 0, Dez 3
    for tag in (5, 6):
        await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 1, tag))
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 3, 10))
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2025, 10, 10))
    for tag in (1, 2, 3):
        await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2025, 12, tag))

    body = (
        await client.get(
            DATEN, headers=h,
            params=_p("vorgaenge.erstellt", gruppierung="monat", vergleich_von="2025-10-01", vergleich_bis="2025-12-31"),
        )
    ).json()
    assert [(z["schluessel"], z["label"], z["wert"], z["vorperiode"]) for z in body["zeilen"]] == [
        ("2026-01", "Jan 2026", 2, 1),
        ("2026-02", "Feb 2026", 0, 0),
        ("2026-03", "Mär 2026", 1, 3),
    ]
    assert body["gesamt"] == 3 and body["vorperiode_gesamt"] == 4
    assert body["art"] == "zeitraum" and body["einheit"] == "anzahl" and body["datumsbezug"] == "erstellt_am"
    assert body["von"] == "2026-01-01" and body["bis"] == "2026-03-31" and body["abgeschnitten"] is False


@pytest.mark.asyncio
async def test_zeitreihe_woche_label_und_ohne_vergleich(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 11, 17))
    body = (
        await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt", gruppierung="woche", von="2026-11-16", bis="2026-11-29"))
    ).json()
    assert [(z["schluessel"], z["label"], z["wert"], z["vorperiode"]) for z in body["zeilen"]] == [
        ("2026-W47", "KW 47", 1, None),
        ("2026-W48", "KW 48", 0, None),
    ]
    assert body["vorperiode_gesamt"] is None


@pytest.mark.asyncio
async def test_nicht_summierbar_luecke_ist_none(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(
        mandant=mandant, kunde=kunde, status="abgeschlossen",
        created_at=_naiv(2026, 1, 1), abgeschlossen_am=_utc(2026, 1, 5),
    )
    body = (await client.get(DATEN, headers=h, params=_p("vorgaenge.durchlaufzeit", gruppierung="monat"))).json()
    assert [z["wert"] for z in body["zeilen"]] == [4.0, None, None]
    leer = (await client.get(DATEN, headers=h, params=_p("vorgaenge.durchlaufzeit", von="2025-01-01", bis="2025-01-31"))).json()
    assert leer["gesamt"] is None and leer["zeilen"] == []


@pytest.mark.asyncio
async def test_kategorie_sortiert_absteigend_und_vorperiode_nach_schluessel(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    alpha = await make_kunde(mandant=mandant, name="Alpha")
    beta = await make_kunde(mandant=mandant, name="Beta")
    await make_vorgang(mandant=mandant, kunde=alpha, created_at=_naiv(2026, 2, 1))
    for _ in range(2):
        await make_vorgang(mandant=mandant, kunde=beta, created_at=_naiv(2026, 2, 1))
    await make_vorgang(mandant=mandant, kunde=alpha, created_at=_naiv(2025, 11, 1))
    body = (
        await client.get(
            DATEN, headers=h,
            params=_p("vorgaenge.erstellt", gruppierung="kunde", vergleich_von="2025-10-01", vergleich_bis="2025-12-31"),
        )
    ).json()
    assert [(z["label"], z["wert"], z["vorperiode"]) for z in body["zeilen"]] == [("Beta", 2, 0), ("Alpha", 1, 1)]


@pytest.mark.asyncio
async def test_gesamt_ohne_zeilen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 2, 1))
    body = (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt"))).json()
    assert body["gruppierung"] == "gesamt" and body["zeilen"] == [] and body["gesamt"] == 1


@pytest.mark.asyncio
async def test_finanzen_ohne_abrechnung_und_kundenbeschraenkt_403(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    _, _, h = await _kopf(client, make_mandant, make_user, mandant=mandant, role="mitarbeiter")
    assert (await client.get(DATEN, headers=h, params=_p("finanzen.umsatz_netto"))).status_code == 403
    assert (await client.get(DATEN, headers=h, params=_p("sales.angebotsquote"))).status_code == 403
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt"))).status_code == 200

    tech = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    await make_kunde_zuweisung(mandant=mandant, kunde=await make_kunde(mandant=mandant), techniker=tech)
    ht = auth_headers(await login(client, tech.email, "pw-123456"))
    assert (await client.get(DATEN, headers=ht, params=_p("finanzen.umsatz_netto"))).status_code == 403
    assert (await client.get(DATEN, headers=ht, params=_p("finanzen.offene_forderungen"))).status_code == 403
    katalog = [k["schluessel"] for k in (await client.get(KATALOG, headers=ht)).json()]
    assert not [s for s in katalog if s.startswith(("finanzen.", "sales."))]


@pytest.mark.asyncio
async def test_umsatz_netto_und_modul_abrechnung_aus(client, make_mandant, make_user, make_kunde):
    mandant, admin, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    async with system_session(grund="test") as s:
        s.add(Rechnung(
            mandant_id=mandant.id, kunde_id=kunde.id, rechnungsnummer="R-1", betrag_netto=Decimal("100.00"),
            mwst_satz=Decimal("19.00"), erstellt_von=admin.id, status="versendet", versendet_am=_utc(2026, 2, 10),
        ))
    body = (await client.get(DATEN, headers=h, params=_p("finanzen.umsatz_netto", gruppierung="monat"))).json()
    assert body["einheit"] == "eur" and body["gesamt"] == 100.0
    assert [z["wert"] for z in body["zeilen"]] == [0, 100.0, 0]

    async with system_session(grund="test") as s:
        (await s.get(Mandant, mandant.id)).deaktivierte_module = ["abrechnung"]
    assert (await client.get(DATEN, headers=h, params=_p("finanzen.umsatz_netto"))).status_code == 403
    assert "finanzen.umsatz_netto" not in [k["schluessel"] for k in (await client.get(KATALOG, headers=h)).json()]


@pytest.mark.asyncio
async def test_offen_stand_nach_status(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="in_arbeit")
    await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")
    # von/bis werden bei Stand-Kennzahlen ignoriert (auch ohne Angabe moeglich)
    body = (
        await client.get(
            DATEN, headers=h,
            params={"kennzahl": "vorgaenge.offen", "gruppierung": "status", "von": "2020-01-01", "bis": "2020-01-02",
                    "vergleich_von": "2019-01-01", "vergleich_bis": "2019-12-31"},
        )
    ).json()
    assert body["art"] == "stand" and body["von"] is None and body["bis"] is None
    assert body["vorperiode_gesamt"] is None and body["datumsbezug"] is None
    assert body["gesamt"] == 3
    assert [(z["schluessel"], z["label"], z["wert"], z["vorperiode"]) for z in body["zeilen"]] == [
        ("neu", "Neu", 2, None), ("in_arbeit", "In Arbeit", 1, None),
    ]
    ohne = (await client.get(DATEN, headers=h, params={"kennzahl": "vorgaenge.offen"})).json()
    assert ohne["gesamt"] == 3


@pytest.mark.asyncio
async def test_ueberfaellig_zaehlt_nur_offene_mit_vergangener_faelligkeit(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, _, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, faelligkeit_am=_utc(2020, 1, 1))
    await make_vorgang(mandant=mandant, kunde=kunde, faelligkeit_am=_utc(2099, 1, 1))
    await make_vorgang(mandant=mandant, kunde=kunde)
    await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen", faelligkeit_am=_utc(2020, 1, 1))
    body = (await client.get(DATEN, headers=h, params={"kennzahl": "vorgaenge.ueberfaellig"})).json()
    assert body["gesamt"] == 1


@pytest.mark.asyncio
async def test_offene_forderungen_alter_feste_reihenfolge(client, make_mandant, make_user, make_kunde):
    from datetime import date, timedelta

    mandant, admin, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Zahler AG")
    heute = date.today()
    async with system_session(grund="test") as s:
        for nummer, faellig in (("R-A", heute - timedelta(days=10)), ("R-B", heute + timedelta(days=5))):
            s.add(Rechnung(
                mandant_id=mandant.id, kunde_id=kunde.id, rechnungsnummer=nummer, betrag_netto=Decimal("100.00"),
                mwst_satz=Decimal("0.00"), erstellt_von=admin.id, status="versendet",
                versendet_am=_utc(2026, 1, 1), faellig_am=faellig,
            ))
    alter = (await client.get(DATEN, headers=h, params={"kennzahl": "finanzen.offene_forderungen", "gruppierung": "alter"})).json()
    assert alter["gesamt"] == 200.0
    assert [(z["schluessel"], z["wert"]) for z in alter["zeilen"]] == [
        ("Nicht fällig", 100.0), ("1-30 Tage", 100.0), ("31-60 Tage", 0.0), ("61-90 Tage", 0.0), ("90+ Tage", 0.0),
    ]
    ueber = (await client.get(DATEN, headers=h, params={"kennzahl": "finanzen.ueberfaellig"})).json()
    assert ueber["gesamt"] == 100.0
    kunden = (await client.get(DATEN, headers=h, params={"kennzahl": "finanzen.offene_forderungen", "gruppierung": "kunde"})).json()
    assert [(z["label"], z["wert"]) for z in kunden["zeilen"]] == [("Zahler AG", 200.0)]
    verb = (await client.get(DATEN, headers=h, params={"kennzahl": "finanzen.verbindlichkeiten"})).json()
    assert verb["gesamt"] == 0


async def _angebote_anlegen(mandant, kunde, admin, versendet, angenommen):
    async with system_session(grund="test") as s:
        for i in range(versendet):
            ok = i < angenommen
            s.add(Angebot(
                mandant_id=mandant.id, kunde_id=kunde.id, angebotsnummer=f"A-{i}", erstellt_von=admin.id,
                status="angenommen" if ok else "versendet", versendet_am=_utc(2026, 2, 3),
                angenommen_am=_utc(2026, 2, 20) if ok else None,
            ))


@pytest.mark.asyncio
async def test_angebotsquote(client, make_mandant, make_user, make_kunde):
    mandant, admin, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)

    leer = (await client.get(DATEN, headers=h, params=_p("sales.angebotsquote"))).json()
    assert leer["gesamt"] is None and leer["einheit"] == "prozent"

    await _angebote_anlegen(mandant, kunde, admin, versendet=4, angenommen=1)
    body = (await client.get(DATEN, headers=h, params=_p("sales.angebotsquote", gruppierung="monat"))).json()
    assert body["gesamt"] == 25.0
    assert [z["wert"] for z in body["zeilen"]] == [None, 25.0, None]
    versendet = (await client.get(DATEN, headers=h, params=_p("sales.angebote_versendet"))).json()
    assert versendet["gesamt"] == 4
    angenommen = (await client.get(DATEN, headers=h, params=_p("sales.angebote_angenommen", gruppierung="kunde"))).json()
    assert angenommen["gesamt"] == 1 and angenommen["zeilen"][0]["wert"] == 1


@pytest.mark.asyncio
async def test_telefonate(client, make_mandant, make_user, make_kunde):
    mandant, admin, h = await _kopf(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    async with system_session(grund="test") as s:
        for sekunden in (120, 180):
            s.add(Telefonat(
                mandant_id=mandant.id, kunde_id=kunde.id, partner_name="x", richtung="ausgehend", ergebnis="erreicht",
                dauer_sekunden=sekunden, beginn=_utc(2026, 2, 3), erfasst_von=admin.id,
            ))
    assert (await client.get(DATEN, headers=h, params=_p("telefonate.anzahl"))).json()["gesamt"] == 2
    dauer = (await client.get(DATEN, headers=h, params=_p("telefonate.dauer", gruppierung="monat"))).json()
    assert dauer["einheit"] == "minuten" and dauer["gesamt"] == 5.0
    assert [z["wert"] for z in dauer["zeilen"]] == [0, 5.0, 0]


@pytest.mark.asyncio
async def test_ungueltige_anfragen(client, make_mandant, make_user):
    _, _, h = await _kopf(client, make_mandant, make_user)
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt", gruppierung="alter"))).status_code == 422
    assert (await client.get(DATEN, headers=h, params={"kennzahl": "vorgaenge.offen", "gruppierung": "monat"})).status_code == 422
    assert (await client.get(DATEN, headers=h, params=_p("gibt.es_nicht"))).status_code == 404
    # Zeitraum-Kennzahlen brauchen von/bis, bis >= von, hoechstens 3 Jahre
    assert (await client.get(DATEN, headers=h, params={"kennzahl": "vorgaenge.erstellt"})).status_code == 422
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt", von="2026-03-01", bis="2026-01-01"))).status_code == 422
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt", von="2020-01-01", bis="2026-01-01"))).status_code == 422
    assert (await client.get(DATEN, headers=h, params=_p("vorgaenge.erstellt", vergleich_von="2025-01-01"))).status_code == 422


# --- Dashboards ------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_crud(client, make_mandant, make_user):
    _, user, h = await _kopf(client, make_mandant, make_user, name="Anna Admin")
    resp = await client.post(DASHBOARDS, headers=h, json={"name": "  Mein Überblick ", "layout": _layout(2), "vorlage": "ueberblick"})
    assert resp.status_code == 201
    d = resp.json()
    assert d["name"] == "Mein Überblick" and d["eigenes"] is True and d["ersteller_name"] == "Anna Admin"
    assert d["fuer_alle"] is False and d["vorlage"] == "ueberblick" and d["sortierung"] == 0
    assert d["layout"]["zeitraum"] == "monat" and len(d["layout"]["widgets"]) == 2
    assert d["layout"]["widgets"][0]["vergleich"] is True

    zweites = (await client.post(DASHBOARDS, headers=h, json={"name": "Zweites", "layout": _layout()})).json()
    assert zweites["sortierung"] == 1
    assert [x["name"] for x in (await client.get(DASHBOARDS, headers=h)).json()] == ["Mein Überblick", "Zweites"]

    neu = _layout(1)
    neu["zeitraum"] = "quartal"
    patch = await client.patch(f"{DASHBOARDS}/{d['id']}", headers=h, json={"name": "Umbenannt", "layout": neu})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Umbenannt" and patch.json()["layout"]["zeitraum"] == "quartal"
    assert patch.json()["fuer_alle"] is False

    # Doppelter Name: beim Anlegen und beim Umbenennen
    dup = await client.post(DASHBOARDS, headers=h, json={"name": "Zweites", "layout": _layout()})
    assert dup.status_code == 409 and "Name" in dup.json()["detail"]
    assert (await client.patch(f"{DASHBOARDS}/{d['id']}", headers=h, json={"name": "Zweites"})).status_code == 409

    assert (await client.delete(f"{DASHBOARDS}/{d['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{DASHBOARDS}/{d['id']}", headers=h)).status_code == 404
    assert [x["name"] for x in (await client.get(DASHBOARDS, headers=h)).json()] == ["Zweites"]


@pytest.mark.asyncio
async def test_dashboard_sichtbarkeit_und_freigabe(client, make_mandant, make_user):
    mandant, admin, h_admin = await _kopf(client, make_mandant, make_user, name="Admin")
    _, custom, h_custom = await _kopf(client, make_mandant, make_user, mandant=mandant, role="mitarbeiter", name="Max Mitarbeiter")

    privat = (await client.post(DASHBOARDS, headers=h_admin, json={"name": "Privat", "layout": _layout()})).json()
    geteilt = await client.post(DASHBOARDS, headers=h_admin, json={"name": "Geteilt", "layout": _layout(), "fuer_alle": True})
    assert geteilt.status_code == 201 and geteilt.json()["fuer_alle"] is True
    eigenes = (await client.post(DASHBOARDS, headers=h_custom, json={"name": "Meins", "layout": _layout()})).json()

    sicht = (await client.get(DASHBOARDS, headers=h_custom)).json()
    # eigene zuerst, danach die geteilten fremden
    assert [(x["name"], x["eigenes"], x["ersteller_name"]) for x in sicht] == [
        ("Meins", True, "Max Mitarbeiter"), ("Geteilt", False, "Admin"),
    ]

    # fremdes persoenliches Dashboard: unsichtbar (404), geteiltes fremdes: sichtbar, aber nicht aenderbar (403)
    assert (await client.patch(f"{DASHBOARDS}/{privat['id']}", headers=h_custom, json={"name": "X"})).status_code == 404
    assert (await client.delete(f"{DASHBOARDS}/{privat['id']}", headers=h_custom)).status_code == 404
    assert (await client.patch(f"{DASHBOARDS}/{geteilt.json()['id']}", headers=h_custom, json={"name": "X"})).status_code == 403
    assert (await client.delete(f"{DASHBOARDS}/{geteilt.json()['id']}", headers=h_custom)).status_code == 403

    # Freigabe fuer alle: nur Admin
    assert (await client.post(DASHBOARDS, headers=h_custom, json={"name": "Frei", "layout": _layout(), "fuer_alle": True})).status_code == 403
    assert (await client.patch(f"{DASHBOARDS}/{eigenes['id']}", headers=h_custom, json={"fuer_alle": True})).status_code == 403
    assert (await client.patch(f"{DASHBOARDS}/{privat['id']}", headers=h_admin, json={"fuer_alle": True})).json()["fuer_alle"] is True
    assert [x["name"] for x in (await client.get(DASHBOARDS, headers=h_custom)).json()] == ["Meins", "Geteilt", "Privat"]


@pytest.mark.asyncio
async def test_dashboard_reihenfolge(client, make_mandant, make_user):
    mandant, _, h = await _kopf(client, make_mandant, make_user, name="Admin")
    _, _, h_fremd = await _kopf(client, make_mandant, make_user, mandant=mandant, role="mitarbeiter")
    ids = {}
    for name in ("A", "B", "C"):
        ids[name] = (await client.post(DASHBOARDS, headers=h, json={"name": name, "layout": _layout()})).json()["id"]
    fremd = (await client.post(DASHBOARDS, headers=h_fremd, json={"name": "Fremd", "layout": _layout()})).json()["id"]

    resp = await client.put(
        f"{DASHBOARDS}/reihenfolge", headers=h,
        json={"ids": [ids["C"], fremd, "00000000-0000-0000-0000-000000000000", ids["A"]]},
    )
    assert resp.status_code == 200
    assert [x["name"] for x in (await client.get(DASHBOARDS, headers=h)).json()] == ["C", "A", "B"]
    # fremdes Dashboard bleibt unveraendert
    assert [(x["name"], x["sortierung"]) for x in (await client.get(DASHBOARDS, headers=h_fremd)).json()] == [("Fremd", 0)]


@pytest.mark.asyncio
async def test_dashboard_layout_validierung(client, make_mandant, make_user):
    _, _, h = await _kopf(client, make_mandant, make_user)
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "Zu viel", "layout": _layout(31)})).status_code == 422
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "Genau", "layout": _layout(30)})).status_code == 201
    kaputt = _layout()
    kaputt["widgets"][0]["darstellung"] = "torte"
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "Kaputt", "layout": kaputt})).status_code == 422
    schluessel = _layout()
    schluessel["widgets"][0]["kennzahl"] = "Ungültig"
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "Kaputt2", "layout": schluessel})).status_code == 422
    # unbekannte, aber wohlgeformte Kennzahl wird gespeichert (Frontend zeigt "nicht mehr verfuegbar")
    unbekannt = _layout()
    unbekannt["widgets"][0]["kennzahl"] = "alt.entfernt"
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "Alt", "layout": unbekannt})).status_code == 201
    assert (await client.post(DASHBOARDS, headers=h, json={"name": "  ", "layout": _layout()})).status_code == 422


@pytest.mark.asyncio
async def test_dashboard_mandantentrennung(client, make_mandant, make_user):
    _, _, h_a = await _kopf(client, make_mandant, make_user, name="Admin A")
    _, _, h_b = await _kopf(client, make_mandant, make_user, name="Admin B")
    privat = (await client.post(DASHBOARDS, headers=h_a, json={"name": "A privat", "layout": _layout()})).json()
    geteilt = (await client.post(DASHBOARDS, headers=h_a, json={"name": "A geteilt", "layout": _layout(), "fuer_alle": True})).json()

    assert (await client.get(DASHBOARDS, headers=h_b)).json() == []
    # Auch ein geteiltes Dashboard endet an der Mandantengrenze (RLS)
    for d in (privat, geteilt):
        assert (await client.patch(f"{DASHBOARDS}/{d['id']}", headers=h_b, json={"name": "X"})).status_code == 404
        assert (await client.delete(f"{DASHBOARDS}/{d['id']}", headers=h_b)).status_code == 404
