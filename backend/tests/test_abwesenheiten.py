"""Abwesenheitsantraege, Urlaubskonto, Freizeitausgleich (docs/konzepte/
ZEITERFASSUNG.md, Abschnitt "Abwesenheiten, Urlaubskonto, Freizeitausgleich")."""
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.user import User
from app.models.zeiterfassung import ZEITERFASSUNG_KATEGORIEN, Zeiterfassung
from app.schemas.zeiterfassung import ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT
from app.services.abwesenheit_service import abwesenheitstage, berechne_konto, summe_tage
from app.services.arbeitszeit_service import ZeitEintrag, berechne_saldo
from tests.conftest import auth_headers, login

BERLIN = ZoneInfo("Europe/Berlin")
D = Decimal


def _soll(gueltig_ab=date(2026, 1, 1), mo=8, di=8, mi=8, do=8, fr=8, sa=0, so=0):
    return SimpleNamespace(
        gueltig_ab=gueltig_ab,
        stunden_mo=D(mo), stunden_di=D(di), stunden_mi=D(mi), stunden_do=D(do),
        stunden_fr=D(fr), stunden_sa=D(sa), stunden_so=D(so),
    )


def _lokal(jahr, monat, tag, std, minute=0):
    return datetime(jahr, monat, tag, std, minute, tzinfo=BERLIN).astimezone(timezone.utc)


# --- reine Funktionen ---------------------------------------------------


def test_tageszaehlung_wochenende_und_feiertag_zaehlen_nicht():
    # Mo 2.3. bis So 8.3., Do 5.3. Feiertag
    tage = abwesenheitstage(date(2026, 3, 2), date(2026, 3, 8), False, False, [_soll()], {date(2026, 3, 5)})
    assert [t.datum.day for t in tage] == [2, 3, 4, 6]
    assert summe_tage(tage) == D("4")
    assert all(t.stunden == D("8") for t in tage)


def test_tageszaehlung_nutzt_persoenliches_soll():
    # Teilzeit: nur Mo und Mi, 5 bzw. 3 Stunden
    zeilen = [_soll(mo=5, di=0, mi=3, do=0, fr=0)]
    tage = abwesenheitstage(date(2026, 3, 2), date(2026, 3, 6), False, False, zeilen, set())
    assert [(t.datum.day, t.stunden) for t in tage] == [(2, D("5")), (4, D("3"))]


def test_tageszaehlung_halbe_tage_erster_und_letzter():
    tage = abwesenheitstage(date(2026, 3, 2), date(2026, 3, 4), True, True, [_soll()], set())
    assert [t.faktor for t in tage] == [D("0.5"), D("1"), D("0.5")]
    assert [t.stunden for t in tage] == [D("4"), D("8"), D("4")]
    assert summe_tage(tage) == D("2")


def test_tageszaehlung_ein_tag_mit_halb_flag_ist_ein_halber_tag():
    for von_flag, bis_flag in ((True, False), (False, True), (True, True)):
        tage = abwesenheitstage(date(2026, 3, 2), date(2026, 3, 2), von_flag, bis_flag, [_soll()], set())
        assert summe_tage(tage) == D("0.5")


def test_tageszaehlung_ohne_arbeitstag_ist_leer():
    assert abwesenheitstage(date(2026, 3, 7), date(2026, 3, 8), False, False, [_soll()], set()) == []
    assert abwesenheitstage(date(2026, 3, 2), date(2026, 3, 6), False, False, [], set()) == []


def test_tageszaehlung_ueber_jahresgrenze():
    # Mo 28.12.2026 bis Di 5.1.2027, Fr 1.1. Feiertag -> 28-31.12. (4) + 4./5.1. (2)
    tage = abwesenheitstage(date(2026, 12, 28), date(2027, 1, 5), False, False, [_soll()], {date(2027, 1, 1)})
    assert summe_tage(tage) == D("6")
    assert sum(1 for t in tage if t.datum.year == 2026) == 4


def test_konto_resturlaub_verfall():
    stichtag = date(2026, 3, 31)
    genommen = [(date(2026, 2, 2), D("1")), (date(2026, 2, 3), D("1")), (date(2026, 6, 1), D("5"))]
    # vor dem Stichtag: Resturlaub noch voll verfuegbar
    vorher = berechne_konto(D("30"), D("5"), stichtag, genommen, [], date(2026, 3, 1))
    assert (vorher.resturlaub_verfallen, vorher.verbleibend) == (D("0"), D("28"))
    # danach: 2 Tage Rest verbraucht, 3 verfallen
    nachher = berechne_konto(D("30"), D("5"), stichtag, genommen, [], date(2026, 4, 1))
    assert nachher.resturlaub_verfallen == D("3")
    assert nachher.genommen == D("7") and nachher.verbleibend == D("25")
    # Stichtag selbst zaehlt noch zum Resturlaub-Zeitraum
    am_tag = berechne_konto(D("30"), D("5"), stichtag, [(stichtag, D("5"))], [], date(2026, 4, 1))
    assert am_tag.resturlaub_verfallen == D("0") and am_tag.verbleibend == D("30")


def test_konto_beantragt_zaehlt_mit_und_minus_ist_erlaubt():
    k = berechne_konto(D("2"), D("0"), None, [(date(2026, 3, 2), D("1"))], [(date(2026, 3, 3), D("2.5"))], date(2026, 3, 1))
    assert (k.genommen, k.beantragt, k.verbleibend) == (D("1"), D("2.5"), D("-1.5"))
    # ohne Stichtag verfaellt Resturlaub nie
    k = berechne_konto(D("10"), D("4"), None, [], [], date(2030, 1, 1))
    assert (k.resturlaub_verfallen, k.verbleibend) == (D("0"), D("14"))


def _e(start, stunden, kategorie):
    return ZeitEintrag(start, start + timedelta(hours=stunden), kategorie)


def test_saldo_freizeitausgleich_ganzer_tag():
    erg = berechne_saldo(
        date(2026, 3, 2), date(2026, 3, 2), [_soll()], set(),
        [_e(_lokal(2026, 3, 2, 8), 8, "freizeitausgleich")], _lokal(2026, 3, 10, 12),
    )
    tag = erg.tage[0]
    assert (tag.soll, tag.ist, tag.saldo, tag.abwesenheit) == (D("8"), D("0"), D("-8"), "freizeitausgleich")
    assert erg.saldo_stunden == D("-8")


def test_saldo_freizeitausgleich_halber_tag_anteilig():
    erg = berechne_saldo(
        date(2026, 3, 2), date(2026, 3, 2), [_soll()], set(),
        [_e(_lokal(2026, 3, 2, 8), 4, "freizeitausgleich")], _lokal(2026, 3, 10, 12),
    )
    assert (erg.tage[0].ist, erg.tage[0].saldo) == (D("4"), D("-4"))
    # Mehrarbeit in der anderen Haelfte zaehlt
    erg = berechne_saldo(
        date(2026, 3, 2), date(2026, 3, 2), [_soll()], set(),
        [_e(_lokal(2026, 3, 2, 8), 4, "freizeitausgleich"), _e(_lokal(2026, 3, 2, 12), 6, "verwaltung")],
        _lokal(2026, 3, 10, 12),
    )
    assert (erg.tage[0].ist, erg.tage[0].saldo) == (D("6"), D("-2"))


def test_urlaub_hat_vorrang_vor_freizeitausgleich_krankheit_vor_beiden():
    e = [_e(_lokal(2026, 3, 2, 8), 4, "freizeitausgleich"), _e(_lokal(2026, 3, 2, 8), 4, "urlaub")]
    erg = berechne_saldo(date(2026, 3, 2), date(2026, 3, 2), [_soll()], set(), e, _lokal(2026, 3, 10, 12))
    assert (erg.tage[0].abwesenheit, erg.tage[0].saldo) == ("urlaub", D("0"))
    erg = berechne_saldo(date(2026, 3, 2), date(2026, 3, 2), [_soll()], set(), [*e, _e(_lokal(2026, 3, 2, 8), 4, "krankheit")], _lokal(2026, 3, 10, 12))
    assert erg.tage[0].abwesenheit == "krankheit"


def test_freizeitausgleich_ist_keine_arbeitszeit_kategorie():
    assert "freizeitausgleich" in ZEITERFASSUNG_KATEGORIEN
    assert "freizeitausgleich" in ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT


# --- API ----------------------------------------------------------------

_SOLL = {"gueltig_ab": "2026-01-01", "stunden_mo": "8", "stunden_di": "8", "stunden_mi": "8",
         "stunden_do": "8", "stunden_fr": "8"}


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


async def _setup(client, make_mandant, make_user):
    """Mandant mit Admin (Soll Mo-Fr 8 h, Feiertag Do 5.3.2026), Mitarbeiter
    ohne Recht (Soll Mo-Fr 8 h) und Buero-Nutzer mit Recht."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", name="Admin")
    ma = await _custom_user(mandant, "Anna", verwalten=False)
    buero = await _custom_user(mandant, "Berta", verwalten=True)
    h_admin, h_ma, h_buero = await _h(client, admin), await _h(client, ma), await _h(client, buero)
    for u in (admin, ma, buero):
        r = await client.put(f"/api/arbeitszeit/soll/{u.id}", headers=h_admin, json=_SOLL)
        assert r.status_code == 200, r.text
    await client.post("/api/arbeitszeit/feiertage", headers=h_admin, json={"datum": "2026-03-05", "bezeichnung": "Test"})
    return SimpleNamespace(mandant=mandant, admin=admin, ma=ma, buero=buero, h_admin=h_admin, h_ma=h_ma, h_buero=h_buero)


async def _eintraege(user_id, kategorie=None, abwesenheit_id=None, geloescht=False):
    async with system_session() as session:
        stmt = select(Zeiterfassung).where(Zeiterfassung.techniker_id == user_id)
        if kategorie:
            stmt = stmt.where(Zeiterfassung.kategorie == kategorie)
        if abwesenheit_id:
            stmt = stmt.where(Zeiterfassung.abwesenheit_id == abwesenheit_id)
        stmt = stmt.where(Zeiterfassung.geloescht_am.is_not(None) if geloescht else Zeiterfassung.geloescht_am.is_(None))
        return list((await session.execute(stmt.order_by(Zeiterfassung.start_at))).scalars().all())


def _antrag(art="urlaub", von="2026-03-02", bis="2026-03-06", **extra):
    return {"art": art, "von": von, "bis": bis, **extra}


@pytest.mark.asyncio
async def test_urlaub_beantragen_genehmigen_erzeugt_zeiteintraege(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    r = await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag(notiz="Skifahren"))
    assert r.status_code == 201, r.text
    antrag = r.json()
    assert antrag["status"] == "offen" and antrag["tage"] == "4.0"  # Do 5.3. Feiertag
    assert antrag["user_name"] == "Anna" and antrag["notiz"] == "Skifahren"
    assert antrag["erstellt_von"] == str(s.ma.id) and antrag["bearbeitet_von"] is None
    assert await _eintraege(s.ma.id) == []  # vor der Genehmigung nichts

    r = await client.post(f"/api/abwesenheiten/{antrag['id']}/genehmigen", headers=s.h_buero)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "genehmigt" and r.json()["bearbeitet_von"] == str(s.buero.id)

    eintraege = await _eintraege(s.ma.id, "urlaub")
    assert len(eintraege) == 4
    assert [e.start_at.astimezone(BERLIN).day for e in eintraege] == [2, 3, 4, 6]
    assert all(e.start_at.astimezone(BERLIN).hour == 8 and (e.ende_at - e.start_at) == timedelta(hours=8) for e in eintraege)
    assert all(str(e.abwesenheit_id) == antrag["id"] and e.vorgang_id is None and not e.abrechenbar for e in eintraege)

    # nochmal genehmigen: kein offener Antrag mehr
    assert (await client.post(f"/api/abwesenheiten/{antrag['id']}/genehmigen", headers=s.h_buero)).status_code == 409
    assert len(await _eintraege(s.ma.id, "urlaub")) == 4


@pytest.mark.asyncio
async def test_halbe_tage_erzeugen_halbes_soll(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    r = await client.post(
        "/api/abwesenheiten", headers=s.h_buero,
        json=_antrag(von="2026-03-02", bis="2026-03-03", halber_tag_von=True, halber_tag_bis=True, user_id=str(s.ma.id)),
    )
    assert r.status_code == 201, r.text
    assert r.json()["tage"] == "1.0" and r.json()["status"] == "genehmigt"
    dauern = [e.ende_at - e.start_at for e in await _eintraege(s.ma.id, "urlaub")]
    assert dauern == [timedelta(hours=4), timedelta(hours=4)]


@pytest.mark.asyncio
async def test_ablehnen_und_zurueckziehen(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    a1 = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).json()
    r = await client.post(f"/api/abwesenheiten/{a1['id']}/ablehnen", headers=s.h_buero, json={"antwort": "Projektphase"})
    assert r.status_code == 200 and r.json()["status"] == "abgelehnt" and r.json()["antwort"] == "Projektphase"
    assert await _eintraege(s.ma.id) == []
    # abgelehnt ist final
    assert (await client.post(f"/api/abwesenheiten/{a1['id']}/zurueckziehen", headers=s.h_ma)).status_code == 409
    assert (await client.post(f"/api/abwesenheiten/{a1['id']}/ablehnen", headers=s.h_buero)).status_code == 409
    # abgelehnter Zeitraum ist wieder frei; Ablehnen ohne Body geht auch
    a2 = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).json()
    r = await client.post(f"/api/abwesenheiten/{a2['id']}/ablehnen", headers=s.h_buero)
    assert r.status_code == 200 and r.json()["antwort"] is None
    # eigenen offenen Antrag zurueckziehen
    a3 = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).json()
    r = await client.post(f"/api/abwesenheiten/{a3['id']}/zurueckziehen", headers=s.h_ma)
    assert r.status_code == 200 and r.json()["status"] == "zurueckgezogen"


@pytest.mark.asyncio
async def test_stornieren_genehmigter_abwesenheit_nur_mit_recht_und_entfernt_eintraege(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    a = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).json()
    await client.post(f"/api/abwesenheiten/{a['id']}/genehmigen", headers=s.h_buero)
    assert len(await _eintraege(s.ma.id, "urlaub")) == 4

    assert (await client.post(f"/api/abwesenheiten/{a['id']}/zurueckziehen", headers=s.h_ma)).status_code == 403
    assert len(await _eintraege(s.ma.id, "urlaub")) == 4

    r = await client.post(f"/api/abwesenheiten/{a['id']}/zurueckziehen", headers=s.h_buero)
    assert r.status_code == 200 and r.json()["status"] == "zurueckgezogen"
    assert await _eintraege(s.ma.id, "urlaub") == []
    geloescht = await _eintraege(s.ma.id, "urlaub", geloescht=True)
    assert len(geloescht) == 4 and all(e.geloescht_von == s.buero.id for e in geloescht)
    # Zeitraum ist wieder frei
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).status_code == 201


@pytest.mark.asyncio
async def test_krankheit_sofort_genehmigt(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    r = await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("krankheit", "2026-03-02", "2026-03-03"))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "genehmigt" and r.json()["tage"] == "2.0"
    assert len(await _eintraege(s.ma.id, "krankheit")) == 2
    # fuer andere nur mit Recht
    r = await client.post(
        "/api/abwesenheiten", headers=s.h_ma, json=_antrag("krankheit", "2026-03-09", "2026-03-09", user_id=str(s.buero.id))
    )
    assert r.status_code == 403
    r = await client.post(
        "/api/abwesenheiten", headers=s.h_buero, json=_antrag("krankheit", "2026-03-09", "2026-03-09", user_id=str(s.ma.id))
    )
    assert r.status_code == 201 and r.json()["status"] == "genehmigt"


@pytest.mark.asyncio
async def test_direkteintrag_durch_berechtigten_fuer_sich_und_andere(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    fuer_sich = await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-03-02", "2026-03-02"))
    assert fuer_sich.status_code == 201 and fuer_sich.json()["status"] == "genehmigt"
    fuer_andere = await client.post(
        "/api/abwesenheiten", headers=s.h_admin,
        json=_antrag("freizeitausgleich", "2026-03-02", "2026-03-02", user_id=str(s.ma.id)),
    )
    assert fuer_andere.status_code == 201 and fuer_andere.json()["status"] == "genehmigt"
    assert fuer_andere.json()["erstellt_von"] == str(s.admin.id) and fuer_andere.json()["user_id"] == str(s.ma.id)
    assert len(await _eintraege(s.buero.id, "urlaub")) == 1
    assert len(await _eintraege(s.ma.id, "freizeitausgleich")) == 1


@pytest.mark.asyncio
async def test_ueberschneidung_409_und_kein_arbeitstag_422(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-03-02", "2026-03-04"))).status_code == 201
    r = await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("krankheit", "2026-03-04", "2026-03-06"))
    assert r.status_code == 409
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-03-01", "2026-03-02"))).status_code == 409
    # angrenzend ist erlaubt
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-03-06", "2026-03-06"))).status_code == 201
    # anderer Nutzer: kein Konflikt
    assert (await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-03-02", "2026-03-04"))).status_code == 201

    # Wochenende, Feiertag
    for von, bis in (("2026-03-07", "2026-03-08"), ("2026-03-05", "2026-03-05")):
        r = await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", von, bis))
        assert r.status_code == 422, r.text
        assert "Arbeitstag" in r.json()["detail"]
    # bis vor von, zu lang
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-04-02", "2026-04-01"))).status_code == 422
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-01-01", "2027-01-02"))).status_code == 422


@pytest.mark.asyncio
async def test_vergangenheit_jahresgrenze_und_kein_doppelanlegen(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    # Von Hand nachgetragener Urlaubseintrag am 29.12.2026 (Di) -> wird nicht verdoppelt
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=s.mandant.id, techniker_id=s.ma.id, kategorie="urlaub",
                start_at=_lokal(2026, 12, 29, 7), ende_at=_lokal(2026, 12, 29, 15),
            )
        )
    r = await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-12-28", "2027-01-05", user_id=str(s.ma.id)))
    assert r.status_code == 201, r.text
    # 28.-31.12. (4) + 4./5.1. (2); 1.1. ist ohne eingetragenen Feiertag Arbeitstag (Fr) -> 7
    assert r.json()["tage"] == "7.0"
    eintraege = await _eintraege(s.ma.id, "urlaub")
    assert len(eintraege) == 7
    assert sum(1 for e in eintraege if e.abwesenheit_id is None) == 1


@pytest.mark.asyncio
async def test_konto_mit_resturlaub_verfall_und_ueberziehen(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    uid = str(s.ma.id)
    r = await client.put(
        f"/api/abwesenheiten/anspruch/{uid}/2026", headers=s.h_buero,
        json={"tage": "30", "resturlaub_tage": "5", "resturlaub_verfaellt_am": "2026-03-31"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["tage"], r.json()["resturlaub_tage"]) == ("30.0", "5.0")
    # ersetzt statt zu verdoppeln
    assert (await client.put(f"/api/abwesenheiten/anspruch/{uid}/2026", headers=s.h_buero, json={"tage": "30", "resturlaub_tage": "5", "resturlaub_verfaellt_am": "2026-03-31"})).status_code == 200

    # genehmigt: 3.-4.3. (2 Tage, vor Stichtag); genehmigt: 8.-10.6. (3); offen: 15.-16.6. (2)
    for von, bis, direkt in (("2026-03-03", "2026-03-04", True), ("2026-06-08", "2026-06-10", True), ("2026-06-15", "2026-06-16", False)):
        h = s.h_buero if direkt else s.h_ma
        body = _antrag("urlaub", von, bis, **({"user_id": uid} if direkt else {}))
        assert (await client.post("/api/abwesenheiten", headers=h, json=body)).status_code == 201
    # Krankheit und Freizeitausgleich zaehlen nicht zum Urlaub
    await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("krankheit", "2026-07-06", "2026-07-07"))

    konto = (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"jahr": 2026})).json()
    assert konto["anspruch"] == "30.0" and konto["resturlaub"] == "5.0"
    assert konto["genommen"] == "5.0" and konto["beantragt"] == "2.0"
    # Stichtag 31.3.2026 liegt in der Vergangenheit: 2 Tage Rest vor dem Stichtag
    # verbraucht, 3 verfallen
    assert konto["resturlaub_verfallen"] == "3.0"
    assert konto["verbleibend"] == "25.0"  # 30 + 5 - 3 - 5 - 2

    # Ueberziehen wird nicht blockiert
    await client.put(f"/api/abwesenheiten/anspruch/{uid}/2026", headers=s.h_buero, json={"tage": "1", "resturlaub_tage": "0"})
    konto = (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"jahr": 2026})).json()
    assert konto["verbleibend"] == "-6.0" and konto["resturlaub_verfaellt_am"] is None
    # anderes Jahr ohne Anspruch/Urlaub
    leer = (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"jahr": 2025})).json()
    assert (D(leer["anspruch"]), D(leer["genommen"]), D(leer["verbleibend"])) == (0, 0, 0)


@pytest.mark.asyncio
async def test_konto_teilt_antrag_ueber_jahresgrenze_nach_jahren(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    uid = str(s.ma.id)
    await client.put(f"/api/abwesenheiten/anspruch/{uid}/2026", headers=s.h_buero, json={"tage": "30"})
    await client.put(f"/api/abwesenheiten/anspruch/{uid}/2027", headers=s.h_buero, json={"tage": "30"})
    r = await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-12-28", "2027-01-05", user_id=uid))
    assert r.status_code == 201
    k26 = (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"jahr": 2026})).json()
    k27 = (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"jahr": 2027})).json()
    assert (k26["genommen"], k27["genommen"]) == ("4.0", "3.0")


@pytest.mark.asyncio
async def test_freizeitausgleich_im_saldo_und_nicht_als_arbeitszeit(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    uid = str(s.ma.id)
    # Mo 2.3. ganzer Tag, Di 3.3. halber Tag
    r = await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("freizeitausgleich", "2026-03-02", "2026-03-02", user_id=uid))
    assert r.status_code == 201
    r = await client.post(
        "/api/abwesenheiten", headers=s.h_buero,
        json=_antrag("freizeitausgleich", "2026-03-03", "2026-03-03", halber_tag_von=True, user_id=uid),
    )
    assert r.status_code == 201
    assert all(e.kategorie == "freizeitausgleich" for e in await _eintraege(s.ma.id))

    r = await client.get("/api/arbeitszeit/saldo", headers=s.h_ma, params={"von": "2026-03-02", "bis": "2026-03-03"})
    assert r.status_code == 200, r.text
    tage = r.json()["tage"]
    assert [(t["soll"], t["ist"], t["saldo"], t["abwesenheit"]) for t in tage] == [
        ("8.00", "0.00", "-8.00", "freizeitausgleich"),
        ("8.00", "4.00", "-4.00", "freizeitausgleich"),
    ]
    assert r.json()["saldo_stunden"] == "-12.00"

    # Statistik zaehlt den Eintrag nicht als Arbeitszeit
    from app.api.routes.zeiterfassung import ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT as ohne

    assert "freizeitausgleich" in ohne


@pytest.mark.asyncio
async def test_rechte_ohne_recht_nur_eigene_und_kein_genehmigen(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    eigen = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-03-02", "2026-03-02"))).json()
    fremd = (await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-03-09", "2026-03-09"))).json()

    liste = (await client.get("/api/abwesenheiten", headers=s.h_ma)).json()
    assert [a["id"] for a in liste] == [eigen["id"]]
    assert (await client.get("/api/abwesenheiten", headers=s.h_ma, params={"user_id": str(s.buero.id)})).status_code == 403
    assert (await client.get("/api/abwesenheiten", headers=s.h_ma, params={"alle": "true"})).status_code == 403
    assert (await client.get("/api/abwesenheiten/konto", headers=s.h_ma, params={"user_id": str(s.buero.id)})).status_code == 403
    assert (await client.get("/api/abwesenheiten/kalender", headers=s.h_ma, params={"von": "2026-03-01", "bis": "2026-03-31"})).status_code == 403
    assert (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag(user_id=str(s.buero.id)))).status_code == 403
    assert (await client.put(f"/api/abwesenheiten/anspruch/{s.ma.id}/2026", headers=s.h_ma, json={"tage": "30"})).status_code == 403
    assert (await client.post(f"/api/abwesenheiten/{eigen['id']}/genehmigen", headers=s.h_ma)).status_code == 403
    assert (await client.post(f"/api/abwesenheiten/{eigen['id']}/ablehnen", headers=s.h_ma)).status_code == 403
    # fremden Antrag zurueckziehen: unsichtbar
    assert (await client.post(f"/api/abwesenheiten/{fremd['id']}/zurueckziehen", headers=s.h_ma)).status_code == 404

    # Berechtigter sieht alles, filtert, und kennt Namen
    alle = (await client.get("/api/abwesenheiten", headers=s.h_buero, params={"alle": "true"})).json()
    assert {a["user_name"] for a in alle} == {"Anna", "Berta"}
    offene = (await client.get("/api/abwesenheiten", headers=s.h_buero, params={"alle": "true", "nur_offene": "true"})).json()
    assert [a["id"] for a in offene] == [eigen["id"]]
    genehmigte = (await client.get("/api/abwesenheiten", headers=s.h_buero, params={"alle": "true", "status": "genehmigt"})).json()
    assert [a["id"] for a in genehmigte] == [fremd["id"]]
    bereich = (await client.get("/api/abwesenheiten", headers=s.h_buero, params={"alle": "true", "von": "2026-03-08", "bis": "2026-03-31"})).json()
    assert [a["id"] for a in bereich] == [fremd["id"]]
    einzeln = (await client.get("/api/abwesenheiten", headers=s.h_buero, params={"user_id": str(s.ma.id)})).json()
    assert [a["id"] for a in einzeln] == [eigen["id"]]
    # ohne alle/user_id sieht auch der Berechtigte nur eigene
    eigene_buero = (await client.get("/api/abwesenheiten", headers=s.h_buero)).json()
    assert [a["id"] for a in eigene_buero] == [fremd["id"]]


@pytest.mark.asyncio
async def test_kalender_nur_genehmigte_und_zeitraumgrenze(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("urlaub", "2026-03-02", "2026-03-03"))  # offen
    await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag("krankheit", "2026-03-09", "2026-03-10"))
    await client.post("/api/abwesenheiten", headers=s.h_buero, json=_antrag("urlaub", "2026-03-30", "2026-04-03"))
    r = await client.get("/api/abwesenheiten/kalender", headers=s.h_buero, params={"von": "2026-03-01", "bis": "2026-03-31"})
    assert r.status_code == 200, r.text
    assert [(e["user_name"], e["art"], e["tage"]) for e in r.json()] == [("Anna", "krankheit", "2.0"), ("Berta", "urlaub", "5.0")]
    assert (await client.get("/api/abwesenheiten/kalender", headers=s.h_buero, params={"von": "2026-01-01", "bis": "2027-01-02"})).status_code == 422
    assert (await client.get("/api/abwesenheiten/kalender", headers=s.h_buero, params={"von": "2026-01-01", "bis": "2027-01-01"})).status_code == 200


@pytest.mark.asyncio
async def test_mandantentrennung(client, make_mandant, make_user):
    s1 = await _setup(client, make_mandant, make_user)
    m2 = await make_mandant(name="Betrieb2")
    a2 = await make_user(mandant=m2, role="mandant_admin", password="pw-123456")
    h2 = await _h(client, a2)
    await client.put(f"/api/arbeitszeit/soll/{a2.id}", headers=h2, json=_SOLL)

    antrag = (await client.post("/api/abwesenheiten", headers=s1.h_ma, json=_antrag())).json()
    assert (await client.get("/api/abwesenheiten", headers=h2, params={"alle": "true"})).json() == []
    assert (await client.get("/api/abwesenheiten", headers=h2, params={"user_id": str(s1.ma.id)})).status_code == 404
    assert (await client.get("/api/abwesenheiten/konto", headers=h2, params={"user_id": str(s1.ma.id)})).status_code == 404
    assert (await client.post("/api/abwesenheiten", headers=h2, json=_antrag(user_id=str(s1.ma.id)))).status_code == 404
    assert (await client.put(f"/api/abwesenheiten/anspruch/{s1.ma.id}/2026", headers=h2, json={"tage": "30"})).status_code == 404
    for aktion in ("genehmigen", "ablehnen", "zurueckziehen"):
        assert (await client.post(f"/api/abwesenheiten/{antrag['id']}/{aktion}", headers=h2)).status_code == 404
    assert (await client.get("/api/abwesenheiten/kalender", headers=h2, params={"von": "2026-03-01", "bis": "2026-03-31"})).json() == []
    # gleicher Zeitraum im anderen Mandanten: kein Konflikt
    assert (await client.post("/api/abwesenheiten", headers=h2, json=_antrag())).status_code == 201


@pytest.mark.asyncio
async def test_neue_tabellen_haben_rls_policy():
    tabellen = ("abwesenheitsantraege", "urlaubsanspruch")
    async with system_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT tablename FROM pg_policies WHERE policyname = 'mandant_isolation' "
                    "AND tablename IN ('abwesenheitsantraege', 'urlaubsanspruch')"
                )
            )
        ).scalars().all()
        assert sorted(rows) == list(tabellen)
        forced = (
            await session.execute(
                text("SELECT relname FROM pg_class WHERE relname IN ('abwesenheitsantraege', 'urlaubsanspruch') AND relforcerowsecurity")
            )
        ).scalars().all()
        assert sorted(forced) == list(tabellen)


def test_migration_0101_up_down_up():
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

    def spalten():
        return {c["name"] for c in inspect(engine).get_columns("zeiterfassung")}

    try:
        command.downgrade(cfg, "0100")
        assert not {"abwesenheitsantraege", "urlaubsanspruch"} & tabellen()
        assert "abwesenheit_id" not in spalten()
        command.upgrade(cfg, "head")
        assert {"abwesenheitsantraege", "urlaubsanspruch"} <= tabellen()
        assert "abwesenheit_id" in spalten()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_zeiterfassung_liste_enthaelt_abwesenheit_id(client, make_mandant, make_user):
    s = await _setup(client, make_mandant, make_user)
    antrag = (await client.post("/api/abwesenheiten", headers=s.h_ma, json=_antrag())).json()
    await client.post(f"/api/abwesenheiten/{antrag['id']}/genehmigen", headers=s.h_buero)
    r = await client.get(
        "/api/zeiterfassung", headers=s.h_admin, params={"techniker_id": str(s.ma.id), "von": "2026-03-01", "bis": "2026-03-31"}
    )
    assert r.status_code == 200, r.text
    urlaub = [e for e in r.json() if e["kategorie"] == "urlaub"]
    assert len(urlaub) == 4 and all(e["abwesenheit_id"] == antrag["id"] for e in urlaub)
