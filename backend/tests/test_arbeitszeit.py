"""Soll-Arbeitszeit, Feiertage, Ueberstundensaldo (docs/konzepte/
ZEITERFASSUNG.md, Abschnitt "Soll-Zeit, Feiertage, Ueberstundensaldo")."""
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.user import User
from app.models.zeiterfassung import Zeiterfassung
from app.services.arbeitszeit_service import (
    ZeitEintrag,
    berechne_saldo,
    feiertage_fuer,
    ostersonntag,
    soll_fuer_tag,
)
from tests.conftest import auth_headers, login

BERLIN = ZoneInfo("Europe/Berlin")
D = Decimal


def _soll(gueltig_ab, mo=0, di=0, mi=0, do=0, fr=0, sa=0, so=0):
    return SimpleNamespace(
        gueltig_ab=gueltig_ab,
        stunden_mo=D(mo), stunden_di=D(di), stunden_mi=D(mi), stunden_do=D(do),
        stunden_fr=D(fr), stunden_sa=D(sa), stunden_so=D(so),
    )


def _lokal(jahr, monat, tag, std, minute=0):
    return datetime(jahr, monat, tag, std, minute, tzinfo=BERLIN).astimezone(timezone.utc)


# --- reine Funktionen ---------------------------------------------------


def test_ostersonntag_bekannte_daten():
    assert ostersonntag(2024) == date(2024, 3, 31)
    assert ostersonntag(2025) == date(2025, 4, 20)
    assert ostersonntag(2026) == date(2026, 4, 5)
    assert ostersonntag(2038) == date(2038, 4, 25)


def test_bewegliche_feiertage_haengen_an_ostern():
    tage = dict(feiertage_fuer(None, 2026))
    assert tage[date(2026, 4, 3)] == "Karfreitag"
    assert tage[date(2026, 4, 6)] == "Ostermontag"
    assert tage[date(2026, 5, 14)] == "Christi Himmelfahrt"
    assert tage[date(2026, 5, 25)] == "Pfingstmontag"
    assert len(tage) == 9  # nur bundesweite


def test_bundesland_unterschiede():
    by = dict(feiertage_fuer("BY", 2026))
    assert by[date(2026, 6, 4)] == "Fronleichnam"
    assert date(2026, 1, 6) in by and date(2026, 11, 1) in by
    assert date(2026, 10, 31) not in by
    sn = dict(feiertage_fuer("SN", 2026))
    assert sn[date(2026, 11, 18)] == "Buß- und Bettag"
    assert date(2026, 10, 31) in sn and date(2026, 6, 4) not in sn
    be = dict(feiertage_fuer("BE", 2026))
    assert date(2026, 3, 8) in be and date(2026, 1, 6) not in be
    # Frauentag MV erst ab 2023, Reformationstag NI erst ab 2018
    assert date(2022, 3, 8) not in dict(feiertage_fuer("MV", 2022))
    assert date(2023, 3, 8) in dict(feiertage_fuer("MV", 2023))
    assert date(2017, 10, 31) not in dict(feiertage_fuer("NI", 2017))
    assert date(2018, 10, 31) in dict(feiertage_fuer("NI", 2018))
    assert date(2026, 9, 20) in dict(feiertage_fuer("TH", 2026))


def test_buss_und_bettag_liegt_immer_vor_dem_23_november():
    for jahr in range(2020, 2031):
        tag = next(d for d, n in feiertage_fuer("SN", jahr) if n == "Buß- und Bettag")
        assert tag.weekday() == 2 and date(jahr, 11, 16) <= tag <= date(jahr, 11, 22)


def test_soll_ohne_zeile_ist_null():
    assert soll_fuer_tag(date(2026, 3, 2), [], set()) == D("0")


def test_soll_gilt_ab_datum_bis_zur_naechsten_zeile():
    zeilen = [_soll(date(2026, 1, 1), mo=8, fr=8), _soll(date(2026, 3, 1), mo=6, fr=4)]
    assert soll_fuer_tag(date(2025, 12, 29), zeilen, set()) == 0  # vor der ersten Zeile
    assert soll_fuer_tag(date(2026, 2, 23), zeilen, set()) == D("8")  # Mo
    assert soll_fuer_tag(date(2026, 2, 28), zeilen, set()) == 0  # Sa
    assert soll_fuer_tag(date(2026, 3, 2), zeilen, set()) == D("6")  # Mo, neue Zeile
    assert soll_fuer_tag(date(2026, 3, 6), zeilen, set()) == D("4")  # Fr, neue Zeile
    # Reihenfolge der Zeilen spielt keine Rolle
    assert soll_fuer_tag(date(2026, 3, 2), zeilen[::-1], set()) == D("6")


def test_soll_an_feiertag_ist_null():
    zeilen = [_soll(date(2026, 1, 1), mo=8)]
    assert soll_fuer_tag(date(2026, 4, 6), zeilen, {date(2026, 4, 6)}) == 0  # Ostermontag


def _e(start, stunden, kategorie="verwaltung", laufend=False):
    return ZeitEintrag(start, None if laufend else start + timedelta(hours=stunden), kategorie)


def test_saldo_ueberstunden_und_unterstunden():
    zeilen = [_soll(date(2026, 1, 1), mo=8, di=8)]
    eintraege = [_e(_lokal(2026, 3, 2, 8), 9), _e(_lokal(2026, 3, 3, 8), 6)]
    erg = berechne_saldo(
        date(2026, 3, 2), date(2026, 3, 3), zeilen, set(), eintraege, _lokal(2026, 3, 10, 12)
    )
    assert [t.saldo for t in erg.tage] == [D("1"), D("-2")]
    assert (erg.soll_stunden, erg.ist_stunden, erg.saldo_stunden) == (D("16"), D("15"), D("-1"))


def test_saldo_pause_zaehlt_nicht_und_fahrzeit_schon():
    zeilen = [_soll(date(2026, 1, 1), mo=8)]
    eintraege = [
        _e(_lokal(2026, 3, 2, 8), 4, "auftrag"),
        _e(_lokal(2026, 3, 2, 12), 1, "pause"),
        _e(_lokal(2026, 3, 2, 13), 2, "fahrzeit"),
    ]
    erg = berechne_saldo(date(2026, 3, 2), date(2026, 3, 2), zeilen, set(), eintraege, _lokal(2026, 3, 10, 12))
    assert erg.tage[0].ist == D("6")


@pytest.mark.parametrize("kategorie", ["urlaub", "krankheit"])
def test_saldo_urlaub_krankheit_zaehlen_als_erfuellt(kategorie):
    zeilen = [_soll(date(2026, 1, 1), mo=8)]
    eintraege = [_e(_lokal(2026, 3, 2, 0), 24, kategorie)]
    erg = berechne_saldo(date(2026, 3, 2), date(2026, 3, 2), zeilen, set(), eintraege, _lokal(2026, 3, 10, 12))
    tag = erg.tage[0]
    assert (tag.soll, tag.ist, tag.saldo, tag.abwesenheit) == (D("8"), D("8"), D("0"), kategorie)
    assert erg.saldo_stunden == 0


def test_saldo_feiertag_hat_kein_soll_gearbeitete_zeit_ist_ueberstunde():
    zeilen = [_soll(date(2026, 1, 1), mo=8)]
    feiertage = {date(2026, 4, 6)}
    eintraege = [_e(_lokal(2026, 4, 6, 9), 3)]
    erg = berechne_saldo(date(2026, 4, 6), date(2026, 4, 6), zeilen, feiertage, eintraege, _lokal(2026, 4, 10, 12))
    tag = erg.tage[0]
    assert tag.feiertag and (tag.soll, tag.ist, tag.saldo) == (D("0"), D("3"), D("3"))


def test_saldo_laufender_eintrag_zaehlt_bis_jetzt():
    zeilen = [_soll(date(2026, 1, 1), mo=8)]
    eintraege = [_e(_lokal(2026, 3, 2, 8), 0, laufend=True)]
    erg = berechne_saldo(date(2026, 3, 2), date(2026, 3, 2), zeilen, set(), eintraege, _lokal(2026, 3, 2, 10, 30))
    assert erg.tage[0].ist == D("2.50")


def test_saldo_tagesgrenze_in_berlin_statt_utc():
    zeilen = [_soll(date(2026, 1, 1), mo=8, di=8)]
    # 01:30 Berlin am Dienstag = 23:30 UTC am Montag -> gehoert zum Dienstag
    eintraege = [_e(datetime(2026, 7, 6, 23, 30, tzinfo=timezone.utc), 1)]
    erg = berechne_saldo(date(2026, 7, 6), date(2026, 7, 7), zeilen, set(), eintraege, _lokal(2026, 7, 10, 12))
    assert [t.ist for t in erg.tage] == [D("0"), D("1")]


# --- API ----------------------------------------------------------------


async def _custom_user(mandant, name, *, verwalten):
    async with system_session() as session:
        typ = AccountTyp(mandant_id=mandant.id, name=f"Typ-{name}", darf_abwesenheiten_verwalten=verwalten)
        session.add(typ)
        await session.flush()
        user = User(
            mandant_id=mandant.id,
            email=f"{name.lower()}@example.de",
            password_hash=hash_password("pw-123456"),
            role="custom",
            account_typ_id=typ.id,
            name=name,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def _h(client, user):
    return auth_headers(await login(client, user.email, "pw-123456"))


_SOLL = {"gueltig_ab": "2026-01-01", "stunden_mo": "8", "stunden_di": "8", "stunden_mi": "8",
         "stunden_do": "8", "stunden_fr": "8"}


@pytest.mark.asyncio
async def test_soll_setzen_lesen_und_ersetzen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = await _h(client, admin)

    assert (await client.get("/api/arbeitszeit/soll", headers=h)).json() == []
    r = await client.put(f"/api/arbeitszeit/soll/{admin.id}", headers=h, json=_SOLL)
    assert r.status_code == 200, r.text
    assert r.json()["stunden_mo"] == "8.00" and r.json()["stunden_sa"] == "0.00"
    await client.put(f"/api/arbeitszeit/soll/{admin.id}", headers=h, json={**_SOLL, "stunden_mo": "6.5"})
    await client.put(f"/api/arbeitszeit/soll/{admin.id}", headers=h, json={**_SOLL, "gueltig_ab": "2026-06-01"})
    zeilen = (await client.get("/api/arbeitszeit/soll", headers=h)).json()
    assert [z["gueltig_ab"] for z in zeilen] == ["2026-06-01", "2026-01-01"]
    assert zeilen[1]["stunden_mo"] == "6.50"


@pytest.mark.asyncio
@pytest.mark.parametrize("wert", ["-1", "24.5", "8.123"])
async def test_soll_ungueltige_stunden_werden_abgelehnt(client, make_mandant, make_user, wert):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    r = await client.put(
        f"/api/arbeitszeit/soll/{admin.id}", headers=await _h(client, admin), json={**_SOLL, "stunden_mo": wert}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rechte_ohne_recht_kein_fremdzugriff_und_kein_schreiben(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    ohne = await _custom_user(mandant, "Ohne", verwalten=False)
    mit = await _custom_user(mandant, "Mit", verwalten=True)
    h_admin, h_ohne, h_mit = await _h(client, admin), await _h(client, ohne), await _h(client, mit)
    await client.put(f"/api/arbeitszeit/soll/{ohne.id}", headers=h_admin, json=_SOLL)

    # Eigenes Soll/Saldo lesen immer
    assert (await client.get("/api/arbeitszeit/soll", headers=h_ohne)).status_code == 200
    p = {"von": "2026-03-02", "bis": "2026-03-03"}
    assert (await client.get("/api/arbeitszeit/saldo", headers=h_ohne, params=p)).status_code == 200
    # Fremdes nicht
    assert (await client.get("/api/arbeitszeit/soll", headers=h_ohne, params={"user_id": str(admin.id)})).status_code == 403
    assert (await client.get("/api/arbeitszeit/saldo", headers=h_ohne, params={**p, "user_id": str(admin.id)})).status_code == 403
    # Schreiben nicht, auch nicht fuer sich selbst
    assert (await client.put(f"/api/arbeitszeit/soll/{ohne.id}", headers=h_ohne, json=_SOLL)).status_code == 403
    assert (await client.post("/api/arbeitszeit/feiertage", headers=h_ohne, json={"datum": "2026-12-24", "bezeichnung": "X"})).status_code == 403
    assert (await client.post("/api/arbeitszeit/feiertage/generieren", headers=h_ohne, json={"jahr": 2026})).status_code == 403
    assert (await client.patch("/api/arbeitszeit/bundesland", headers=h_ohne, json={"bundesland": "BY"})).status_code == 403
    # Feiertage und Bundesland lesen darf jeder
    assert (await client.get("/api/arbeitszeit/feiertage", headers=h_ohne, params={"jahr": 2026})).status_code == 200
    assert (await client.get("/api/arbeitszeit/bundesland", headers=h_ohne)).status_code == 200

    # Mit Recht: fremdes lesen/schreiben, Feiertage und Bundesland pflegen
    assert (await client.get("/api/arbeitszeit/soll", headers=h_mit, params={"user_id": str(ohne.id)})).status_code == 200
    assert (await client.put(f"/api/arbeitszeit/soll/{ohne.id}", headers=h_mit, json=_SOLL)).status_code == 200
    assert (await client.patch("/api/arbeitszeit/bundesland", headers=h_mit, json={"bundesland": "BY"})).json() == {"bundesland": "BY"}
    assert (await client.post("/api/arbeitszeit/feiertage", headers=h_mit, json={"datum": "2026-12-24", "bezeichnung": "Heiligabend"})).status_code == 201


@pytest.mark.asyncio
async def test_me_spiegelt_recht(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    ohne = await _custom_user(mandant, "Ohne", verwalten=False)
    mit = await _custom_user(mandant, "Mit", verwalten=True)
    flags = {}
    for u in (admin, ohne, mit):
        flags[u.name] = (await client.get("/api/auth/me", headers=await _h(client, u))).json()["darf_abwesenheiten_verwalten"]
    assert flags == {admin.name: True, "Ohne": False, "Mit": True}


@pytest.mark.asyncio
async def test_account_typ_schalter_setzbar(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = await _h(client, admin)
    r = await client.post("/api/account-typen", headers=h, json={"name": "Büro", "darf_abwesenheiten_verwalten": True})
    assert r.status_code == 201 and r.json()["darf_abwesenheiten_verwalten"] is True
    r = await client.patch(f"/api/account-typen/{r.json()['id']}", headers=h, json={"darf_abwesenheiten_verwalten": False})
    assert r.json()["darf_abwesenheiten_verwalten"] is False


@pytest.mark.asyncio
async def test_feiertage_generieren_idempotent_und_bearbeitbar(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = await _h(client, admin)
    assert (await client.patch("/api/arbeitszeit/bundesland", headers=h, json={"bundesland": "BY"})).status_code == 200
    assert (await client.patch("/api/arbeitszeit/bundesland", headers=h, json={"bundesland": "XX"})).status_code == 422

    r = await client.post("/api/arbeitszeit/feiertage/generieren", headers=h, json={"jahr": 2026})
    erste = r.json()
    assert r.status_code == 200 and erste["angelegt"] == len(erste["feiertage"]) == len(feiertage_fuer("BY", 2026))

    # Eigene Aenderungen ueberleben einen zweiten Lauf
    ostermontag = next(f for f in erste["feiertage"] if f["datum"] == "2026-04-06")
    assert (await client.delete(f"/api/arbeitszeit/feiertage/{ostermontag['id']}", headers=h)).status_code == 204
    await client.post("/api/arbeitszeit/feiertage", headers=h, json={"datum": "2026-12-24", "bezeichnung": "Heiligabend"})
    zweite = (await client.post("/api/arbeitszeit/feiertage/generieren", headers=h, json={"jahr": 2026})).json()
    assert zweite["angelegt"] == 1 and zweite["uebersprungen"] == erste["angelegt"] - 1
    assert len(zweite["feiertage"]) == erste["angelegt"] + 1  # Heiligabend dazu, Ostermontag wieder da
    dritte = (await client.post("/api/arbeitszeit/feiertage/generieren", headers=h, json={"jahr": 2026})).json()
    assert dritte["angelegt"] == 0

    dup = await client.post("/api/arbeitszeit/feiertage", headers=h, json={"datum": "2026-12-24", "bezeichnung": "Nochmal"})
    assert dup.status_code == 409
    liste = (await client.get("/api/arbeitszeit/feiertage", headers=h, params={"jahr": 2025})).json()
    assert liste == []


async def _eintrag(mandant, user, start, ende, kategorie="verwaltung"):
    async with system_session() as session:
        session.add(
            Zeiterfassung(mandant_id=mandant.id, techniker_id=user.id, start_at=start, ende_at=ende, kategorie=kategorie)
        )
        await session.flush()


@pytest.mark.asyncio
async def test_saldo_endpunkt_gesamt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = await _h(client, admin)
    await client.put(f"/api/arbeitszeit/soll/{admin.id}", headers=h, json=_SOLL)
    await client.post("/api/arbeitszeit/feiertage", headers=h, json={"datum": "2026-03-05", "bezeichnung": "Test-Feiertag"})
    # Mo 9 h, Di Urlaub, Mi 7 h, Do Feiertag (0 h), Fr nichts
    await _eintrag(mandant, admin, _lokal(2026, 3, 2, 8), _lokal(2026, 3, 2, 17))
    await _eintrag(mandant, admin, _lokal(2026, 3, 3, 0), _lokal(2026, 3, 4, 0), "urlaub")
    await _eintrag(mandant, admin, _lokal(2026, 3, 4, 8), _lokal(2026, 3, 4, 15))

    r = await client.get("/api/arbeitszeit/saldo", headers=h, params={"von": "2026-03-02", "bis": "2026-03-06"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["saldo"] for t in body["tage"]] == ["1.00", "0.00", "-1.00", "0.00", "-8.00"]
    assert body["tage"][1]["abwesenheit"] == "urlaub" and body["tage"][3]["feiertag"] is True
    assert body["tage"][0]["abwesenheit"] is None
    assert (body["soll_stunden"], body["ist_stunden"], body["saldo_stunden"]) == ("32.00", "24.00", "-8.00")


@pytest.mark.asyncio
async def test_saldo_laufender_eintrag_und_bereichsgrenze(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = await _h(client, admin)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    await _eintrag(mandant, admin, start, None)
    tag = start.astimezone(BERLIN).date().isoformat()
    body = (await client.get("/api/arbeitszeit/saldo", headers=h, params={"von": tag, "bis": tag})).json()
    assert D(body["ist_stunden"]) >= D("2.00")

    ok = await client.get("/api/arbeitszeit/saldo", headers=h, params={"von": "2026-01-01", "bis": "2027-01-01"})
    assert ok.status_code == 200  # 366 Tage
    zu_lang = await client.get("/api/arbeitszeit/saldo", headers=h, params={"von": "2026-01-01", "bis": "2027-01-02"})
    assert zu_lang.status_code == 422
    verkehrt = await client.get("/api/arbeitszeit/saldo", headers=h, params={"von": "2026-02-01", "bis": "2026-01-01"})
    assert verkehrt.status_code == 422


@pytest.mark.asyncio
async def test_mandantentrennung_soll_feiertage_saldo(client, make_mandant, make_user):
    m1, m2 = await make_mandant(name="Betrieb1"), await make_mandant(name="Betrieb2")
    a1 = await make_user(mandant=m1, role="mandant_admin", password="pw-123456")
    a2 = await make_user(mandant=m2, role="mandant_admin", password="pw-123456")
    h1, h2 = await _h(client, a1), await _h(client, a2)
    await client.put(f"/api/arbeitszeit/soll/{a1.id}", headers=h1, json=_SOLL)
    f = (await client.post("/api/arbeitszeit/feiertage", headers=h1, json={"datum": "2026-12-24", "bezeichnung": "Intern"})).json()

    assert (await client.get("/api/arbeitszeit/soll", headers=h2)).json() == []
    assert (await client.get("/api/arbeitszeit/feiertage", headers=h2, params={"jahr": 2026})).json() == []
    # Fremder Mandant: Nutzer ist unsichtbar (404), Feiertag nicht loeschbar
    assert (await client.get("/api/arbeitszeit/soll", headers=h2, params={"user_id": str(a1.id)})).status_code == 404
    assert (await client.put(f"/api/arbeitszeit/soll/{a1.id}", headers=h2, json=_SOLL)).status_code == 404
    assert (await client.get("/api/arbeitszeit/saldo", headers=h2, params={"von": "2026-03-02", "bis": "2026-03-02", "user_id": str(a1.id)})).status_code == 404
    assert (await client.delete(f"/api/arbeitszeit/feiertage/{f['id']}", headers=h2)).status_code == 404
    # Gleiches Datum im anderen Mandanten ist kein Konflikt
    assert (await client.post("/api/arbeitszeit/feiertage", headers=h2, json={"datum": "2026-12-24", "bezeichnung": "Eigen"})).status_code == 201
    assert len((await client.get("/api/arbeitszeit/feiertage", headers=h1, params={"jahr": 2026})).json()) == 1


@pytest.mark.asyncio
async def test_neue_tabellen_haben_rls_policy():
    from sqlalchemy import text

    async with system_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT tablename FROM pg_policies WHERE policyname = 'mandant_isolation' "
                    "AND tablename IN ('arbeitszeit_soll', 'feiertage')"
                )
            )
        ).scalars().all()
        assert sorted(rows) == ["arbeitszeit_soll", "feiertage"]
        forced = (
            await session.execute(
                text("SELECT relname FROM pg_class WHERE relname IN ('arbeitszeit_soll', 'feiertage') AND relforcerowsecurity")
            )
        ).scalars().all()
        assert sorted(forced) == ["arbeitszeit_soll", "feiertage"]


def test_migration_0100_up_down_up():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    backend = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(backend, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend, "alembic"))
    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)

    def tabellen():
        return set(inspect(engine).get_table_names())

    try:
        command.downgrade(cfg, "0099")
        assert not {"arbeitszeit_soll", "feiertage"} & tabellen()
        assert "bundesland" not in {c["name"] for c in inspect(engine).get_columns("mandanten")}
        assert "darf_abwesenheiten_verwalten" not in {c["name"] for c in inspect(engine).get_columns("account_typen")}
        command.upgrade(cfg, "head")
        assert {"arbeitszeit_soll", "feiertage"} <= tabellen()
        assert "bundesland" in {c["name"] for c in inspect(engine).get_columns("mandanten")}
    finally:
        engine.dispose()
