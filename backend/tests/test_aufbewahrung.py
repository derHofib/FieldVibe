"""Aufbewahrungsfristen nach Belegart, Sperre beim endgueltigen Loeschen, Loeschvorschlaege."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.db.session import system_session, tenant_session
from app.models.angebot import Angebot
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import aufbewahrung_service as auf
from app.services import papierkorb_service
from tests.conftest import auth_headers, login


# --- reine Fristberechnung ------------------------------------------------------


@pytest.mark.parametrize(
    ("belegart", "entstehung", "erwartet"),
    [
        ("rechnung", date(2025, 1, 1), date(2033, 12, 31)),  # 8 Jahre ab Ende des Entstehungsjahres
        ("rechnung", date(2025, 12, 31), date(2033, 12, 31)),  # Jahresende: selbes Fristende
        ("rechnung", date(2024, 12, 31), date(2032, 12, 31)),  # Vortag des Jahreswechsels
        ("rechnung", date(2024, 2, 29), date(2032, 12, 31)),  # Schalttag
        ("buchungsbeleg", date(2026, 6, 15), date(2034, 12, 31)),
        ("geschaeftsbrief", date(2026, 6, 15), date(2032, 12, 31)),  # 6 Jahre
        ("angebot", date(2020, 2, 29), date(2026, 12, 31)),  # Schalttag, 6 Jahre
        ("buch_jahresabschluss", date(2025, 3, 1), date(2035, 12, 31)),  # 10 Jahre
        # Uebergang BEG IV: bis Belegjahr 2014 blieb es bei 10 Jahren, ab 2015 gelten 8.
        ("rechnung", date(2014, 12, 31), date(2024, 12, 31)),
        ("rechnung", date(2015, 1, 1), date(2023, 12, 31)),
        ("buchungsbeleg", date(2014, 5, 5), date(2024, 12, 31)),
        # Geschaeftsbriefe waren schon immer 6 Jahre: keine Uebergangsregel.
        ("geschaeftsbrief", date(2014, 5, 5), date(2020, 12, 31)),
    ],
)
def test_fristende(belegart, entstehung, erwartet):
    assert auf.fristende(belegart, entstehung) == erwartet


def test_fristende_ist_immer_ein_31_dezember_und_deterministisch():
    for art in auf.AUFBEWAHRUNG_JAHRE:
        for tag in (date(2020, 1, 1), date(2024, 2, 29), date(2030, 12, 31)):
            ende = auf.fristende(art, tag)
            assert (ende.month, ende.day) == (12, 31)
            assert ende == auf.fristende(art, tag)


def test_grenze_des_ablaufs():
    ende = date(2033, 12, 31)
    assert auf.ist_abgelaufen(ende, date(2033, 12, 31)) is False  # letzter Aufbewahrungstag
    assert auf.ist_abgelaufen(ende, date(2034, 1, 1)) is True


def test_entstehung_in_der_betriebszeitzone():
    # 31.12. 23:30 UTC ist in Berlin schon der 1.1. des Folgejahres -> Frist ein Jahr spaeter.
    r = SimpleNamespace(status="versendet", versendet_am=datetime(2024, 12, 31, 23, 30, tzinfo=timezone.utc), created_at=None)
    assert auf.aufbewahrung_fuer("rechnung", r).fristende == date(2033, 12, 31)
    spaet = SimpleNamespace(status="versendet", versendet_am=datetime(2024, 12, 31, 22, 30, tzinfo=timezone.utc), created_at=None)
    assert auf.aufbewahrung_fuer("rechnung", spaet).fristende == date(2032, 12, 31)


def test_entwuerfe_und_andere_entitaeten_haben_keine_frist():
    assert auf.aufbewahrung_fuer("rechnung", SimpleNamespace(status="entwurf")) is None
    assert auf.aufbewahrung_fuer("eingangsrechnung", SimpleNamespace(status="entwurf")) is None
    assert auf.aufbewahrung_fuer("angebot", SimpleNamespace(status="entwurf")) is None
    assert auf.aufbewahrung_fuer("kunde", SimpleNamespace(status="aktiv")) is None


# --- Sperre beim endgueltigen Loeschen -----------------------------------------------


async def _rechnung_im_papierkorb(mandant, kunde, admin, *, versendet: date, mit_position=True) -> Rechnung:
    async with system_session() as session:
        r = Rechnung(
            mandant_id=mandant.id, kunde_id=kunde.id, rechnungsnummer=f"R-{versendet.isoformat()}",
            betrag_netto=Decimal("10"), mwst_satz=Decimal("19"), status="versendet", erstellt_von=admin.id,
            versendet_am=datetime(versendet.year, versendet.month, versendet.day, 12, tzinfo=timezone.utc),
            geloescht_am=datetime.now(timezone.utc), geloescht_von=admin.id,
        )
        session.add(r)
        await session.flush()
        if mit_position:
            session.add(
                RechnungPosition(mandant_id=mandant.id, rechnung_id=r.id, position=1, beschreibung="x",
                                 menge=Decimal("1"), einheit="Stk", einzelpreis=Decimal("10"))
            )
        return r


@pytest.mark.asyncio
async def test_purge_verweigert_bis_zum_fristende_und_erlaubt_danach(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    r = await _rechnung_im_papierkorb(mandant, kunde, admin, versendet=date(2025, 6, 1))
    fristende = date(2033, 12, 31)

    for heute in (date(2026, 1, 1), date(2033, 12, 31)):
        with pytest.raises(papierkorb_service.GobdLoeschsperre) as exc:
            async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
                await papierkorb_service.purge(session, entity_typ="rechnung", entity_id=r.id, heute=heute)
        assert exc.value.fristende == fristende
        assert "31.12.2033" in str(exc.value)
    async with system_session() as session:
        assert await session.get(Rechnung, r.id) is not None

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        assert await papierkorb_service.purge(session, entity_typ="rechnung", entity_id=r.id, heute=date(2034, 1, 1)) is True
    async with system_session() as session:
        assert await session.get(Rechnung, r.id) is None
        assert (await session.execute(select(RechnungPosition).where(RechnungPosition.rechnung_id == r.id))).first() is None


@pytest.mark.asyncio
async def test_angebot_ist_geschaeftsbrief_sechs_jahre_entwurf_nicht(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    async with system_session() as session:
        versendet = Angebot(
            mandant_id=mandant.id, kunde_id=kunde.id, angebotsnummer="A-1", status="versendet", erstellt_von=admin.id,
            versendet_am=datetime(2026, 3, 1, tzinfo=timezone.utc), geloescht_am=datetime.now(timezone.utc), geloescht_von=admin.id,
        )
        entwurf = Angebot(
            mandant_id=mandant.id, kunde_id=kunde.id, angebotsnummer="A-2", status="entwurf", erstellt_von=admin.id,
            geloescht_am=datetime.now(timezone.utc), geloescht_von=admin.id,
        )
        session.add_all([versendet, entwurf])
        await session.flush()
        versendet_id, entwurf_id = versendet.id, entwurf.id
    with pytest.raises(papierkorb_service.GobdLoeschsperre) as exc:
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            await papierkorb_service.purge(session, entity_typ="angebot", entity_id=versendet_id, heute=date(2030, 1, 1))
    assert exc.value.fristende == date(2032, 12, 31)
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        assert await papierkorb_service.purge(session, entity_typ="angebot", entity_id=versendet_id, heute=date(2033, 1, 1))
        assert await papierkorb_service.purge(session, entity_typ="angebot", entity_id=entwurf_id, heute=date(2026, 1, 1))


@pytest.mark.asyncio
async def test_eingangsrechnung_fristbeginn_ist_der_eingang(make_mandant, make_user):
    mandant = await make_mandant()
    async with system_session() as session:
        e = Eingangsrechnung(
            mandant_id=mandant.id, lieferant_name="L", rechnungsnummer_lieferant="1", rechnungsdatum=date(2025, 12, 20),
            eingegangen_am=date(2026, 1, 3), status="offen", betrag_netto=Decimal("1"),
        )
        session.add(e)
        await session.flush()
        assert auf.aufbewahrung_fuer("eingangsrechnung", e).fristende == date(2034, 12, 31)


@pytest.mark.asyncio
async def test_api_sperre_nennt_fristende_und_protokolliert_loeschung(client, make_mandant, make_user, make_kunde):
    """DSGVO-Konflikt: Loeschbegehren fuer einen Kunden -> Kunde und Belege bleiben gesperrt im
    Papierkorb (Art. 17 Abs. 3 lit. b DSGVO), mit Fristende in der Meldung; nach Fristablauf geht es."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    ho = auth_headers(await login(client, operativ.email, "pw-123456"))

    r = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "10"})).json()
    await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})
    assert (await client.delete(f"/api/kunden/{kunde.id}", headers=h)).status_code == 204

    sperre = await client.delete(f"/api/papierkorb/kunde/{kunde.id}", headers=ho)
    assert sperre.status_code == 409
    detail = sperre.json()["detail"]
    assert "Aufbewahrungspflicht" in detail and f"31.12.{date.today().year + 8}" in detail and "Art. 17 Abs. 3 lit. b DSGVO" in detail

    # Frist kuenstlich abgelaufen: Beleg war vor 10 Jahren -> Kunde samt Beleg loeschbar, Protokoll mit Belegdaten.
    async with system_session() as session:
        await session.execute(text("ALTER TABLE rechnungen DISABLE TRIGGER trg_rechnungen_festschreibung"))
        await session.execute(text("UPDATE rechnungen SET versendet_am = now() - interval '10 years' WHERE id = :i"), {"i": r["id"]})
        await session.execute(text("ALTER TABLE rechnungen ENABLE TRIGGER trg_rechnungen_festschreibung"))
    # Der Beleg selbst liegt nicht im Papierkorb: erst legt der Admin ihn nach der Vorschlagsliste
    # dorthin, dann loescht ihn das Papierkorb-Konto, zuletzt der Kunde.
    assert (await client.post(f"/api/aufbewahrung/loeschvorschlaege/rechnung/{r['id']}/in-papierkorb", headers=h)).status_code == 204
    assert (await client.delete(f"/api/papierkorb/rechnung/{r['id']}", headers=ho)).status_code == 204
    ok = await client.delete(f"/api/papierkorb/kunde/{kunde.id}", headers=ho)
    assert ok.status_code == 204, ok.text
    eintraege = (await client.get("/api/audit", params={"aktion": "papierkorb_endgueltig"}, headers=h)).json()["eintraege"]
    beleg = next(e for e in eintraege if e["entity_type"] == "rechnung")
    assert beleg["payload"]["beleg_nummer"] == r["rechnungsnummer"] and beleg["payload"]["gobd_belegart"] == "rechnung"
    assert beleg["payload"]["fristende"].endswith("-12-31")


# --- Loeschvorschlagsliste ---------------------------------------------------------


@pytest.mark.asyncio
async def test_loeschvorschlaege_nur_abgelaufene_und_nur_nach_bestaetigung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))

    alt = await _rechnung_im_papierkorb(mandant, kunde, admin, versendet=date(2015, 3, 1))
    jung = await _rechnung_im_papierkorb(mandant, kunde, admin, versendet=date.today())
    async with system_session() as session:
        await session.execute(text("UPDATE rechnungen SET geloescht_am = NULL, geloescht_von = NULL"))  # beide aktiv

    liste = (await client.get("/api/aufbewahrung/loeschvorschlaege", headers=h)).json()
    assert [e["id"] for e in liste["eintraege"]] == [str(alt.id)]
    assert liste["eintraege"][0]["fristende"] == "2023-12-31" and liste["eintraege"][0]["im_papierkorb"] is False
    assert liste["gesamt"] == 1 and liste["stichtag"] == papierkorb_service.heute_lokal().isoformat()

    # Nichts wird automatisch geloescht; Bestaetigung legt nur in den Papierkorb ...
    async with system_session() as session:
        assert (await session.get(Rechnung, alt.id)).geloescht_am is None
    assert (await client.post(f"/api/aufbewahrung/loeschvorschlaege/rechnung/{jung.id}/in-papierkorb", headers=h)).status_code == 409
    assert (await client.post(f"/api/aufbewahrung/loeschvorschlaege/rechnung/{alt.id}/in-papierkorb", headers=h)).status_code == 204
    async with system_session() as session:
        assert (await session.get(Rechnung, alt.id)).geloescht_am is not None
    liste = (await client.get("/api/aufbewahrung/loeschvorschlaege", headers=h)).json()
    assert liste["eintraege"][0]["im_papierkorb"] is True
    audit = (await client.get("/api/audit", params={"aktion": "aufbewahrung_in_papierkorb"}, headers=h)).json()
    assert audit["gesamt"] == 1

    # ... und endgueltig loescht erst ein Papierkorb-Konto.
    assert (await client.delete(f"/api/papierkorb/rechnung/{alt.id}", headers=h)).status_code == 403  # mandant_admin darf nicht purgen
    # Rechte
    th = auth_headers(await login(client, techniker.email, "pw-123456"))
    assert (await client.get("/api/aufbewahrung/loeschvorschlaege", headers=th)).status_code == 403
    fristen = (await client.get("/api/aufbewahrung/fristen", headers=h)).json()
    assert {f["belegart"]: f["jahre"] for f in fristen} == {
        "buchungsbeleg": 8, "rechnung": 8, "geschaeftsbrief": 6, "angebot": 6, "buch_jahresabschluss": 10
    }
