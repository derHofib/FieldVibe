from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.projekt import Projekt
from app.models.rechnung import Rechnung
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login

URL = "/api/statistik/aggregat"


def _utc(jahr, monat, tag, stunde=12):
    return datetime(jahr, monat, tag, stunde, tzinfo=timezone.utc)


def _naiv(jahr, monat, tag, stunde=12):
    # created_at ist im ORM ohne timezone=True gemappt (siehe test_statistik.py).
    return datetime(jahr, monat, tag, stunde)


async def _admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    return mandant, admin, auth_headers(token)


async def _rechnung(mandant, kunde, admin, nummer, netto, **kwargs):
    async with system_session(grund="test") as session:
        r = Rechnung(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            rechnungsnummer=nummer,
            betrag_netto=Decimal(netto),
            mwst_satz=Decimal("19.00"),
            erstellt_von=admin.id,
            **kwargs,
        )
        session.add(r)
        await session.flush()
        await session.refresh(r)
        return r


def _params(**kw):
    basis = {"bereich": "vorgaenge", "kennzahl": "anzahl_erstellt", "gruppierung": "monat", "von": "2026-01-01", "bis": "2026-12-31"}
    basis.update(kw)
    return basis


def _wert_je(body):
    return {z["schluessel"]: z["wert"] for z in body["zeilen"]}


@pytest.mark.asyncio
async def test_anzahl_erstellt_nach_monat_und_woche(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 3, 2))
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 3, 20))
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 5, 4))
    # Ausserhalb des Zeitraums
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2025, 12, 31))

    body = (await client.get(URL, headers=h, params=_params())).json()
    assert body["datumsbezug"] == "erstellt_am"
    assert [z["schluessel"] for z in body["zeilen"]] == ["2026-03", "2026-05"]
    assert _wert_je(body) == {"2026-03": 2, "2026-05": 1}
    assert body["gesamt"] == 3
    assert body["zeilen"][0]["label"] == "2026-03"

    woche = (await client.get(URL, headers=h, params=_params(gruppierung="woche"))).json()
    assert [z["schluessel"] for z in woche["zeilen"]] == ["2026-W10", "2026-W12", "2026-W19"]
    assert woche["zeilen"][0]["label"] == "KW 10/2026"


@pytest.mark.asyncio
async def test_anzahl_abgeschlossen_und_durchlaufzeit(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(
        mandant=mandant, kunde=kunde, status="abgeschlossen",
        created_at=_naiv(2026, 3, 1), abgeschlossen_am=_utc(2026, 3, 5),
    )
    await make_vorgang(
        mandant=mandant, kunde=kunde, status="abgeschlossen",
        created_at=_naiv(2026, 3, 1), abgeschlossen_am=_utc(2026, 3, 9),
    )
    # Abschluss vor Anlage: zaehlt als abgeschlossen, aber nicht in die Durchlaufzeit.
    await make_vorgang(
        mandant=mandant, kunde=kunde, status="abgeschlossen",
        created_at=_naiv(2026, 3, 10), abgeschlossen_am=_utc(2026, 3, 8),
    )
    await make_vorgang(mandant=mandant, kunde=kunde, status="in_arbeit", created_at=_naiv(2026, 3, 1))

    anzahl = (await client.get(URL, headers=h, params=_params(kennzahl="anzahl_abgeschlossen"))).json()
    assert anzahl["datumsbezug"] == "abgeschlossen_am"
    assert _wert_je(anzahl) == {"2026-03": 3}

    dauer = (await client.get(URL, headers=h, params=_params(kennzahl="durchlaufzeit_tage"))).json()
    assert _wert_je(dauer) == {"2026-03": 6.0}
    assert dauer["gesamt"] == 6.0


@pytest.mark.asyncio
async def test_gruppierungen_vorgaenge(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    t1 = await make_user(mandant=mandant, role="techniker", name="Tina Tech")
    kunde_a = await make_kunde(mandant=mandant, name="Alpha GmbH")
    kunde_b = await make_kunde(mandant=mandant, name="Beta AG")
    async with system_session(grund="test") as session:
        projekt = Projekt(mandant_id=mandant.id, name="Rollout Nord", erstellt_von=t1.id)
        session.add(projekt)
        await session.flush()
        projekt_id = projekt.id
    zeit = _naiv(2026, 6, 1)
    await make_vorgang(mandant=mandant, kunde=kunde_a, zugewiesener_user_id=t1.id, status="in_arbeit",
                       leistungstyp="wartung", prioritaet=2, projekt_id=projekt_id, created_at=zeit)
    await make_vorgang(mandant=mandant, kunde=kunde_a, zugewiesener_user_id=t1.id, status="in_arbeit",
                       leistungstyp="wartung", prioritaet=2, created_at=zeit)
    await make_vorgang(mandant=mandant, kunde=kunde_b, status="neu", leistungstyp="stoerung", prioritaet=5, created_at=zeit)

    def holen(gruppierung, **kw):
        return client.get(URL, headers=h, params=_params(gruppierung=gruppierung, **kw))

    techniker = (await holen("techniker")).json()
    assert [(z["label"], z["wert"]) for z in techniker["zeilen"]] == [("Tina Tech", 2), ("Nicht zugewiesen", 1)]
    assert techniker["zeilen"][0]["schluessel"] == str(t1.id)
    assert techniker["zeilen"][1]["schluessel"] == "ohne"

    kunde = (await holen("kunde")).json()
    assert [(z["label"], z["wert"]) for z in kunde["zeilen"]] == [("Alpha GmbH", 2), ("Beta AG", 1)]

    status = (await holen("status")).json()
    assert [(z["schluessel"], z["label"], z["wert"]) for z in status["zeilen"]] == [
        ("in_arbeit", "In Arbeit", 2), ("neu", "Neu", 1)
    ]

    leistung = (await holen("leistungstyp")).json()
    assert [(z["schluessel"], z["label"], z["wert"]) for z in leistung["zeilen"]] == [
        ("wartung", "Wartung", 2), ("stoerung", "Störung", 1)
    ]

    prio = (await holen("prioritaet")).json()
    assert _wert_je(prio) == {"2": 2, "5": 1}

    projekte = (await holen("projekt")).json()
    assert [(z["label"], z["wert"]) for z in projekte["zeilen"]] == [("Ohne Projekt", 2), ("Rollout Nord", 1)]

    # Filter
    gefiltert = (await holen("status", kunde_id=str(kunde_b.id))).json()
    assert _wert_je(gefiltert) == {"neu": 1}
    gefiltert = (await holen("kunde", techniker_id=str(t1.id))).json()
    assert gefiltert["gesamt"] == 2
    gefiltert = (await holen("kunde", projekt_id=str(projekt_id))).json()
    assert gefiltert["gesamt"] == 1
    gefiltert = (await holen("kunde", status="neu")).json()
    assert gefiltert["gesamt"] == 1


@pytest.mark.asyncio
async def test_arbeitszeit_stunden(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    t1 = await make_user(mandant=mandant, role="techniker", name="Tina Tech")
    t2 = await make_user(mandant=mandant, role="techniker", name="Tom Tech")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session(grund="test") as session:
        def zeile(techniker, start, ende, **kw):
            return Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=techniker.id,
                start_at=start, ende_at=ende, **kw,
            )
        session.add_all([
            zeile(t1, _utc(2026, 4, 1, 8), _utc(2026, 4, 1, 10)),
            zeile(t1, _utc(2026, 4, 2, 8), _utc(2026, 4, 2, 9)),
            zeile(t2, _utc(2026, 5, 2, 8), _utc(2026, 5, 2, 12)),
            # zaehlt nicht: Fahrzeit, laufender Timer, ausserhalb, soft-geloescht
            zeile(t1, _utc(2026, 4, 3, 8), _utc(2026, 4, 3, 9), kategorie="fahrzeit"),
            zeile(t1, _utc(2026, 4, 4, 8), None),
            zeile(t1, _utc(2025, 4, 4, 8), _utc(2025, 4, 4, 9)),
            zeile(t1, _utc(2026, 4, 5, 8), _utc(2026, 4, 5, 20), geloescht_am=_utc(2026, 4, 6)),
        ])

    p = _params(kennzahl="arbeitszeit_stunden")
    monat = (await client.get(URL, headers=h, params=p)).json()
    assert monat["datumsbezug"] == "zeiterfassung_start"
    assert _wert_je(monat) == {"2026-04": 3.0, "2026-05": 4.0}
    assert monat["gesamt"] == 7.0

    je_techniker = (await client.get(URL, headers=h, params={**p, "gruppierung": "techniker"})).json()
    assert [(z["label"], z["wert"]) for z in je_techniker["zeilen"]] == [("Tom Tech", 4.0), ("Tina Tech", 3.0)]

    nur_t1 = (await client.get(URL, headers=h, params={**p, "techniker_id": str(t1.id)})).json()
    assert nur_t1["gesamt"] == 3.0


@pytest.mark.asyncio
async def test_arbeitszeit_nur_eigene_fuer_techniker(client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung):
    mandant = await make_mandant()
    t1 = await make_user(mandant=mandant, role="techniker", name="Tina", password="pw-123456")
    t2 = await make_user(mandant=mandant, role="techniker", name="Tom")
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=t1)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session(grund="test") as session:
        for techniker, stunden in ((t1, 2), (t2, 5)):
            session.add(Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=techniker.id,
                start_at=_utc(2026, 4, 1, 6), ende_at=_utc(2026, 4, 1, 6 + stunden),
            ))
    h = auth_headers(await login(client, t1.email, "pw-123456"))
    body = (await client.get(URL, headers=h, params=_params(kennzahl="arbeitszeit_stunden"))).json()
    assert body["gesamt"] == 2.0


@pytest.mark.asyncio
async def test_rechnungen_umsatz_storno_gutschrift_entwurf(client, make_mandant, make_user, make_kunde):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde_a = await make_kunde(mandant=mandant, name="Alpha GmbH")
    kunde_b = await make_kunde(mandant=mandant, name="Beta AG")

    normal = await _rechnung(mandant, kunde_a, admin, "R-1", "1000.00", status="versendet", versendet_am=_utc(2026, 3, 10))
    await _rechnung(mandant, kunde_b, admin, "R-2", "500.00", status="bezahlt", versendet_am=_utc(2026, 3, 11))
    # Original storniert + Storno-Beleg: hebt sich auf, zaehlt nicht als Rechnung
    original = await _rechnung(mandant, kunde_b, admin, "R-3", "200.00", status="storniert", versendet_am=_utc(2026, 4, 1))
    await _rechnung(
        mandant, kunde_b, admin, "R-4", "-200.00", status="versendet", versendet_am=_utc(2026, 4, 2),
        ist_storno=True, storniert_rechnung_id=original.id,
    )
    # Gutschrift mindert den Umsatz, ist aber keine Rechnung
    await _rechnung(
        mandant, kunde_a, admin, "G-1", "-100.00", status="versendet", versendet_am=_utc(2026, 4, 3),
        rechnungsart="gutschrift", bezug_rechnung_id=normal.id,
    )
    # Entwurf und soft-geloeschte Rechnung zaehlen nie
    await _rechnung(mandant, kunde_a, admin, "R-5", "9999.00", status="entwurf")
    await _rechnung(
        mandant, kunde_a, admin, "R-6", "7777.00", status="versendet", versendet_am=_utc(2026, 4, 4),
        geloescht_am=_utc(2026, 4, 5),
    )

    p = {"bereich": "rechnungen", "gruppierung": "monat", "von": "2026-01-01", "bis": "2026-12-31"}
    netto = (await client.get(URL, headers=h, params={**p, "kennzahl": "umsatz_netto"})).json()
    assert netto["datumsbezug"] == "versendet_am"
    assert _wert_je(netto) == {"2026-03": 1500.0, "2026-04": -100.0}
    assert netto["gesamt"] == 1400.0

    brutto = (await client.get(URL, headers=h, params={**p, "kennzahl": "umsatz_brutto"})).json()
    assert brutto["gesamt"] == pytest.approx(1400 * 1.19, abs=0.01)

    anzahl = (await client.get(URL, headers=h, params={**p, "kennzahl": "anzahl"})).json()
    assert _wert_je(anzahl) == {"2026-03": 2}
    assert anzahl["gesamt"] == 2

    je_kunde = (await client.get(URL, headers=h, params={**p, "kennzahl": "umsatz_netto", "gruppierung": "kunde"})).json()
    assert [(z["label"], z["wert"]) for z in je_kunde["zeilen"]] == [("Alpha GmbH", 900.0), ("Beta AG", 500.0)]

    je_status = (await client.get(URL, headers=h, params={**p, "kennzahl": "anzahl", "gruppierung": "status"})).json()
    assert [(z["schluessel"], z["label"], z["wert"]) for z in je_status["zeilen"]] == [
        ("bezahlt", "Bezahlt", 1), ("versendet", "Versendet", 1)
    ]

    nur_b = (await client.get(URL, headers=h, params={**p, "kennzahl": "umsatz_netto", "kunde_id": str(kunde_b.id)})).json()
    assert nur_b["gesamt"] == 500.0


@pytest.mark.asyncio
async def test_soft_geloeschte_vorgaenge_zaehlen_nicht(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 3, 2))
    await make_vorgang(mandant=mandant, kunde=kunde, created_at=_naiv(2026, 3, 2), geloescht_am=_utc(2026, 3, 3))
    body = (await client.get(URL, headers=h, params=_params())).json()
    assert body["gesamt"] == 1


@pytest.mark.asyncio
async def test_mandantentrennung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant_a, admin_a, _ = await _admin(client, make_mandant, make_user)
    kunde_a = await make_kunde(mandant=mandant_a)
    await make_vorgang(mandant=mandant_a, kunde=kunde_a, created_at=_naiv(2026, 3, 2))
    await _rechnung(mandant_a, kunde_a, admin_a, "R-1", "1000.00", status="versendet", versendet_am=_utc(2026, 3, 10))

    _, _, h_b = await _admin(client, make_mandant, make_user)
    vorgaenge = (await client.get(URL, headers=h_b, params=_params())).json()
    assert vorgaenge["zeilen"] == [] and vorgaenge["gesamt"] == 0
    rechnungen = (await client.get(URL, headers=h_b, params=_params(bereich="rechnungen", kennzahl="umsatz_netto"))).json()
    assert rechnungen["zeilen"] == [] and rechnungen["gesamt"] == 0


@pytest.mark.asyncio
async def test_kundenbeschraenkung(client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung):
    mandant = await make_mandant()
    tech = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Alpha")
    kunde_b = await make_kunde(mandant=mandant, name="Beta")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde_a, techniker=tech)
    await make_vorgang(mandant=mandant, kunde=kunde_a, created_at=_naiv(2026, 3, 2))
    await make_vorgang(mandant=mandant, kunde=kunde_b, created_at=_naiv(2026, 3, 2))
    await make_vorgang(mandant=mandant, kunde=kunde_b, created_at=_naiv(2026, 3, 3))
    h = auth_headers(await login(client, tech.email, "pw-123456"))

    body = (await client.get(URL, headers=h, params=_params(gruppierung="kunde"))).json()
    assert [(z["label"], z["wert"]) for z in body["zeilen"]] == [("Alpha", 1)]
    assert body["gesamt"] == 1

    # Auch ein ausdruecklich angefragter fremder Kunde liefert nichts
    fremd = (await client.get(URL, headers=h, params=_params(kunde_id=str(kunde_b.id)))).json()
    assert fremd["gesamt"] == 0

    # Rechnungsumsaetze sind fuer Konten mit Kundenbeschraenkung komplett gesperrt
    resp = await client.get(URL, headers=h, params=_params(bereich="rechnungen", kennzahl="umsatz_netto"))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rechnungen_ohne_recht_403(client, make_mandant, make_user):
    mandant = await make_mandant()
    # "mitarbeiter" hat statistik.sehen, aber kein abrechnung.sehen
    user = await make_user(mandant=mandant, role="mitarbeiter", password="pw-123456")
    h = auth_headers(await login(client, user.email, "pw-123456"))
    p = _params(bereich="rechnungen", kennzahl="umsatz_netto")
    assert (await client.get(URL, headers=h, params=p)).status_code == 403
    assert (await client.get(URL, headers=h, params=_params())).status_code == 200


@pytest.mark.asyncio
async def test_rechnungen_ohne_modul_403_und_statistik_modul(client, make_mandant, make_user):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    p = _params(bereich="rechnungen", kennzahl="umsatz_netto")
    assert (await client.get(URL, headers=h, params=p)).status_code == 200

    async with system_session(grund="test") as session:
        m = await session.get(Mandant, mandant.id)
        m.deaktivierte_module = ["abrechnung"]
    assert (await client.get(URL, headers=h, params=p)).status_code == 403
    assert (await client.get(URL, headers=h, params=_params())).status_code == 200

    async with system_session(grund="test") as session:
        m = await session.get(Mandant, mandant.id)
        m.deaktivierte_module = ["statistik"]
    assert (await client.get(URL, headers=h, params=_params())).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aenderung",
    [
        {"bereich": "rechnungen", "kennzahl": "anzahl_erstellt"},
        {"bereich": "vorgaenge", "kennzahl": "umsatz_netto"},
        {"bereich": "rechnungen", "kennzahl": "anzahl", "gruppierung": "techniker"},
        {"bereich": "rechnungen", "kennzahl": "anzahl", "gruppierung": "woche"},
        {"gruppierung": "unbekannt"},
        {"von": "2026-12-31", "bis": "2026-01-01"},
        {"von": "2020-01-01", "bis": "2023-01-02"},
        {"status": "gibt_es_nicht"},
        {"bereich": "rechnungen", "kennzahl": "anzahl", "gruppierung": "monat", "status": "versendet"},
    ],
)
async def test_ungueltige_abfragen_422(client, make_mandant, make_user, aenderung):
    _, _, h = await _admin(client, make_mandant, make_user)
    resp = await client.get(URL, headers=h, params=_params(**aenderung))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_drei_jahre_genau_erlaubt_und_meldung_deutsch(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    ok = await client.get(URL, headers=h, params=_params(von="2023-01-01", bis="2026-01-01"))
    assert ok.status_code == 200
    zu_lang = await client.get(URL, headers=h, params=_params(von="2023-01-01", bis="2026-01-02"))
    assert zu_lang.status_code == 422
    assert "3 Jahre" in zu_lang.json()["detail"]
    falsch = await client.get(URL, headers=h, params=_params(kennzahl="umsatz_netto"))
    assert "passt nicht zum Bereich" in falsch.json()["detail"]


@pytest.mark.asyncio
async def test_ohne_anmeldung_abgewiesen(client):
    resp = await client.get(URL, params=_params())
    assert resp.status_code in (401, 403)
