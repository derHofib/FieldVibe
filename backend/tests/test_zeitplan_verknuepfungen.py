"""Zeitplan Phase 2: Abhaengigkeitsarten (API), verknuepfte Vorgaenge,
Materiallieferung (Bestellung/Liefertermin), Fremdgewerk (Partner) samt
Partnerportal und Auswahl-Endpunkte."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.bestellung import Bestellung
from app.models.lieferant import Lieferant
from app.models.termin import Termin
from app.models.user import User
from tests.conftest import auth_headers, login
from tests.test_partner import _make_zugang, _partner_login
from tests.test_zeitplan_api import _admin, _element, _finde, _projekt, _url, _verbinde
from app.services.organigramm_sync_service import besetzung_pflegen


async def _bestellung(mandant, admin, *, liefertermin=None, nummer=None, lieferant_name=None, **kw) -> Bestellung:
    async with system_session() as session:
        lieferant_id = None
        if lieferant_name:
            lf = Lieferant(mandant_id=mandant.id, name=lieferant_name)
            session.add(lf)
            await session.flush()
            lieferant_id = lf.id
        b = Bestellung(
            mandant_id=mandant.id,
            bestellnummer=nummer or f"B-{uuid.uuid4().hex[:6]}",
            erstellt_von=admin.id,
            liefertermin=liefertermin,
            lieferant_id=lieferant_id,
            **kw,
        )
        session.add(b)
        await session.flush()
        await session.refresh(b)
        return b


# --- Abhaengigkeitsarten ----------------------------------------------------


@pytest.mark.asyncio
async def test_abhaengigkeit_art_anlegen_aendern_und_anwenden(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-10", ende_am="2026-06-14")
    zp = await _element(client, h, pid, "schritt", "B", start_am="2026-06-01", ende_am="2026-06-03")
    a, b = _finde(zp, "A"), _finde(zp, "B")

    r = await client.post(
        _url(pid, "/abhaengigkeiten"),
        headers=h,
        json={"vorgaenger_id": a["id"], "nachfolger_id": b["id"], "art": "anfang_anfang", "versatz_tage": 1},
    )
    assert r.status_code == 200, r.text
    zp = r.json()
    assert zp["abhaengigkeiten"][0]["art"] == "anfang_anfang"
    assert (_finde(zp, "B")["start_am"], _finde(zp, "B")["ende_am"]) == ("2026-06-11", "2026-06-13")
    abh = zp["abhaengigkeiten"][0]["id"]

    # nur art aendern: ende_ende -> Ende >= 14 + 1 = 15 (B endet 13 -> +2)
    r = await client.patch(_url(pid, f"/abhaengigkeiten/{abh}"), headers=h, json={"art": "ende_ende"})
    zp = r.json()
    assert zp["abhaengigkeiten"][0]["art"] == "ende_ende"
    assert zp["abhaengigkeiten"][0]["versatz_tage"] == 1
    assert (_finde(zp, "B")["start_am"], _finde(zp, "B")["ende_am"]) == ("2026-06-13", "2026-06-15")

    # art + versatz gemeinsam
    r = await client.patch(
        _url(pid, f"/abhaengigkeiten/{abh}"), headers=h, json={"art": "ende_anfang", "versatz_tage": 0}
    )
    zp = r.json()
    assert _finde(zp, "B")["start_am"] == "2026-06-15"  # EA: Start >= 14 + 1

    # leerer Body / unbekannte Art
    assert (await client.patch(_url(pid, f"/abhaengigkeiten/{abh}"), headers=h, json={})).status_code == 422
    assert (await client.patch(_url(pid, f"/abhaengigkeiten/{abh}"), headers=h, json={"art": "x"})).status_code == 422


@pytest.mark.asyncio
async def test_default_art_ende_anfang_und_zyklus_unabhaengig_von_art(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-02")
    zp = await _element(client, h, pid, "schritt", "B", start_am="2026-06-03", ende_am="2026-06-04")
    a, b = _finde(zp, "A"), _finde(zp, "B")
    zp = (await _verbinde(client, h, pid, a, b)).json()
    assert zp["abhaengigkeiten"][0]["art"] == "ende_anfang"
    r = await client.post(
        _url(pid, "/abhaengigkeiten"),
        headers=h,
        json={"vorgaenger_id": b["id"], "nachfolger_id": a["id"], "art": "ende_ende"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_ende_ende_im_modus_immer_ueber_api(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    await client.patch(_url(pid, "/einstellungen"), headers=h, json={"verschiebe_modus": "immer"})
    await _element(client, h, pid, "schritt", "A", start_am="2026-06-01", ende_am="2026-06-05")
    zp = await _element(client, h, pid, "schritt", "B", start_am="2026-06-03", ende_am="2026-06-09")
    a, b = _finde(zp, "A"), _finde(zp, "B")
    await client.post(
        _url(pid, "/abhaengigkeiten"),
        headers=h,
        json={"vorgaenger_id": a["id"], "nachfolger_id": b["id"], "art": "ende_ende"},
    )
    zp = (await client.patch(_url(pid, f"/elemente/{a['id']}"), headers=h, json={"ende_am": "2026-06-08"})).json()
    assert (_finde(zp, "B")["start_am"], _finde(zp, "B")["ende_am"]) == ("2026-06-06", "2026-06-12")


# --- Verknuepfter Vorgang ---------------------------------------------------


@pytest.mark.asyncio
async def test_vorgang_verknuepfen_status_und_termine(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    v = await make_vorgang(mandant=mandant, kunde=kunde, titel="Rohre verlegen", status="in_arbeit")
    pid = await _projekt(client, h)

    zp = await _element(client, h, pid, "schritt", "Installation", start_am="2026-06-01", vorgang_id=str(v.id))
    el = _finde(zp, "Installation")
    assert el["vorgang"] == {
        "id": str(v.id), "vorgangsnummer": v.vorgangsnummer, "titel": "Rohre verlegen", "status": "in_arbeit"
    }
    assert el["termine"] == [] and el["erledigt"] is False and el["fortschritt"] == 0

    jetzt = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc)
    async with system_session() as session:
        for i, (name, geloescht) in enumerate([("Spaeter", None), ("Frueh", None), ("Weg", jetzt)]):
            start = jetzt + timedelta(days=1 if name == "Spaeter" else 0)
            session.add(
                Termin(
                    mandant_id=mandant.id, vorgang_id=v.id, techniker_id=admin.id, erstellt_von=admin.id,
                    titel=name, start_at=start, ende_at=start + timedelta(hours=2), geloescht_am=geloescht,
                )
            )
    zp = (await client.get(_url(pid), headers=h)).json()
    termine = _finde(zp, "Installation")["termine"]
    assert [t["start"][:10] for t in termine] == ["2026-06-02", "2026-06-03"]
    assert termine[0]["techniker_name"] == admin.name and termine[0]["ende"] is not None

    # Status abgeschlossen -> erledigt, Fortschritt 100 im Read
    async with system_session() as session:
        obj = await session.get(type(v), v.id)
        obj.status = "abgeschlossen"
    el = _finde((await client.get(_url(pid), headers=h)).json(), "Installation")
    assert el["erledigt"] is True and el["fortschritt"] == 100

    async with system_session() as session:
        obj = await session.get(type(v), v.id)
        obj.status = "storniert"
    el = _finde((await client.get(_url(pid), headers=h)).json(), "Installation")
    assert el["erledigt"] is False and el["vorgang"]["status"] == "storniert"

    # Loesen
    zp = (await client.patch(_url(pid, f"/elemente/{el['id']}"), headers=h, json={"vorgang_id": None})).json()
    assert _finde(zp, "Installation")["vorgang"] is None and _finde(zp, "Installation")["termine"] == []


@pytest.mark.asyncio
async def test_vorgang_verknuepfen_regeln(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    v = await make_vorgang(mandant=mandant, kunde=kunde)
    gel = await make_vorgang(mandant=mandant, kunde=kunde, geloescht_am=datetime.now(timezone.utc))
    fremd_mandant = await make_mandant()
    fremd_kunde = await make_kunde(mandant=fremd_mandant)
    fremd = await make_vorgang(mandant=fremd_mandant, kunde=fremd_kunde)
    pid = await _projekt(client, h)
    pid2 = await _projekt(client, h, "Zweites")

    await _element(client, h, pid, "schritt", "S1", vorgang_id=str(v.id))
    # doppelt im selben Projekt -> 400, in anderem Projekt erlaubt
    r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "schritt", "titel": "S2", "vorgang_id": str(v.id)})
    assert r.status_code == 400
    zp = await _element(client, h, pid, "schritt", "S3")
    r = await client.patch(_url(pid, f"/elemente/{_finde(zp, 'S3')['id']}"), headers=h, json={"vorgang_id": str(v.id)})
    assert r.status_code == 400
    await _element(client, h, pid2, "schritt", "Andere", vorgang_id=str(v.id))

    for vid in (str(gel.id), str(fremd.id), str(uuid.uuid4())):
        r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "schritt", "titel": "X", "vorgang_id": vid})
        assert r.status_code == 400, vid

    # nur Schritte
    for typ in ("meilenstein", "phase"):
        r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": typ, "titel": "M", "vorgang_id": str(v.id)})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_vorgang_auswahl_sortierung_filter_und_zuweisung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    k_ok, k_nein = await make_kunde(mandant=mandant, name="Ok"), await make_kunde(mandant=mandant, name="Nein")
    pid = await _projekt(client, h)
    v_fremd = await make_vorgang(mandant=mandant, kunde=k_ok, titel="Heizung Altbau")
    v_proj = await make_vorgang(mandant=mandant, kunde=k_ok, titel="Dach Neubau", projekt_id=uuid.UUID(pid))
    v_nein = await make_vorgang(mandant=mandant, kunde=k_nein, titel="Heizung Keller")
    await make_vorgang(mandant=mandant, kunde=k_ok, titel="Geloescht", geloescht_am=datetime.now(timezone.utc))
    andere = await make_mandant()
    await make_vorgang(mandant=andere, kunde=await make_kunde(mandant=andere), titel="Heizung fremd")

    r = await client.get(_url(pid, "/auswahl/vorgaenge"), headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["id"] == str(v_proj.id) and body[0]["gehoert_zum_projekt"] is True
    assert {x["id"] for x in body} == {str(v_proj.id), str(v_fremd.id), str(v_nein.id)}
    assert all(x["gehoert_zum_projekt"] is False for x in body[1:])
    assert set(body[0]) == {"id", "vorgangsnummer", "titel", "status", "gehoert_zum_projekt"}

    body = (await client.get(_url(pid, "/auswahl/vorgaenge?q=heizung"), headers=h)).json()
    assert {x["id"] for x in body} == {str(v_fremd.id), str(v_nein.id)}
    body = (await client.get(_url(pid, f"/auswahl/vorgaenge?q={v_proj.vorgangsnummer}"), headers=h)).json()
    assert [x["id"] for x in body] == [str(v_proj.id)]
    assert len((await client.get(_url(pid, "/auswahl/vorgaenge?limit=1"), headers=h)).json()) == 1
    assert (await client.get(_url(pid, "/auswahl/vorgaenge?q=%25"), headers=h)).json() == []

    # nur_zugewiesene_kunden: Custom-Typ mit projekte sehen/bearbeiten
    async with system_session() as session:
        at = AccountTyp(mandant_id=mandant.id, name="Eingeschraenkt", nur_zugewiesene_kunden=True)
        session.add(at)
        await session.flush()
        for aktion in ("sehen", "bearbeiten"):
            session.add(AccountTypRecht(account_typ_id=at.id, bereich="projekte", aktion=aktion, erlaubt=True))
        user = User(
            mandant_id=mandant.id, email=f"{uuid.uuid4().hex[:8]}@example.de", password_hash=hash_password("pw-123456"),
            role="custom", account_typ_id=at.id, name="Eingeschraenkt",
        )
        session.add(user)
        await session.flush()
        await besetzung_pflegen(session, user, neu=True)
        email = user.email
    token = await login(client, email, "pw-123456")
    h2 = auth_headers(token)
    assert (await client.get(_url(pid, "/auswahl/vorgaenge"), headers=h2)).json() == []

    from app.models.kunde_zuweisung import KundeZuweisung

    async with system_session() as session:
        session.add(KundeZuweisung(mandant_id=mandant.id, kunde_id=k_ok.id, user_id=user.id))
    body = (await client.get(_url(pid, "/auswahl/vorgaenge"), headers=h2)).json()
    assert {x["id"] for x in body} == {str(v_proj.id), str(v_fremd.id)}
    # Verknuepfen eines nicht zugewiesenen Kunden-Vorgangs -> 400
    r = await client.post(_url(pid, "/elemente"), headers=h2, json={"typ": "schritt", "titel": "X", "vorgang_id": str(v_nein.id)})
    assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h2, json={"typ": "schritt", "titel": "X", "vorgang_id": str(v_fremd.id)})
    assert r.status_code == 200


# --- Materiallieferung ------------------------------------------------------


@pytest.mark.asyncio
async def test_bestellung_verknuepfen_datum_gesperrt(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin, liefertermin=date(2026, 6, 10), nummer="B-1", lieferant_name="Grosshandel")
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "meilenstein", "Lieferung", bestellung_id=str(b.id))
    ms = _finde(zp, "Lieferung")
    assert (ms["start_am"], ms["ende_am"]) == ("2026-06-10", "2026-06-10")
    assert ms["datum_gesperrt"] is True
    assert ms["bestellung"] == {
        "id": str(b.id), "bestellnummer": "B-1", "status": "entwurf", "liefertermin": "2026-06-10",
        "lieferant_name": "Grosshandel",
    }

    for body in ({"start_am": "2026-06-12"}, {"ende_am": "2026-06-12"}):
        r = await client.patch(_url(pid, f"/elemente/{ms['id']}"), headers=h, json=body)
        assert r.status_code == 400 and "Liefertermin" in r.json()["detail"]
    # Datum beim Anlegen mit Bestellung -> 400; falscher Typ -> 400
    r = await client.post(_url(pid, "/elemente"), headers=h,
                          json={"typ": "meilenstein", "titel": "M", "start_am": "2026-06-01", "bestellung_id": str(b.id)})
    assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "schritt", "titel": "S", "bestellung_id": str(b.id)})
    assert r.status_code == 400

    # Loesen -> Datum bleibt, wieder editierbar
    zp = (await client.patch(_url(pid, f"/elemente/{ms['id']}"), headers=h, json={"bestellung_id": None})).json()
    ms = _finde(zp, "Lieferung")
    assert ms["bestellung"] is None and ms["datum_gesperrt"] is False and ms["start_am"] == "2026-06-10"
    r = await client.patch(_url(pid, f"/elemente/{ms['id']}"), headers=h, json={"start_am": "2026-06-12"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_bestellung_ohne_liefertermin_und_fremde_bestellung(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin)
    fremd = await make_mandant()
    fremd_admin = await make_user(mandant=fremd, role="mandant_admin", password="pw-123456")
    bf = await _bestellung(fremd, fremd_admin, liefertermin=date(2026, 6, 1))
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "meilenstein", "L", bestellung_id=str(b.id))
    assert _finde(zp, "L")["start_am"] is None and _finde(zp, "L")["datum_gesperrt"] is True
    r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "meilenstein", "titel": "X", "bestellung_id": str(bf.id)})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_liefertermin_aenderung_propagiert_inklusive_nachfolger(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin, liefertermin=date(2026, 6, 10))
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "meilenstein", "Lieferung", bestellung_id=str(b.id))
    zp = await _element(client, h, pid, "schritt", "Einbau", start_am="2026-06-10", ende_am="2026-06-12")
    ms, einbau = _finde(zp, "Lieferung"), _finde(zp, "Einbau")
    r = await _verbinde(client, h, pid, ms, einbau)
    assert r.status_code == 200
    bh = h

    r = await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"liefertermin": "2026-06-20"})
    assert r.status_code == 200 and r.json()["liefertermin"] == "2026-06-20"
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Lieferung")["start_am"] == "2026-06-20"
    assert (_finde(zp, "Einbau")["start_am"], _finde(zp, "Einbau")["ende_am"]) == ("2026-06-20", "2026-06-22")

    # Vorziehen: bei_konflikt laesst Nachfolger stehen
    await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"liefertermin": "2026-06-15"})
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Lieferung")["start_am"] == "2026-06-15"
    assert _finde(zp, "Einbau")["start_am"] == "2026-06-20"

    # Modus immer zieht mit
    await client.patch(_url(pid, "/einstellungen"), headers=h, json={"verschiebe_modus": "immer"})
    await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"liefertermin": "2026-06-12"})
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Einbau")["start_am"] == "2026-06-17"

    # Liefertermin entfernt -> Meilenstein ohne Datum, Abhaengigkeit bleibt
    r = await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"liefertermin": None})
    assert r.json()["liefertermin"] is None
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Lieferung")["start_am"] is None and _finde(zp, "Lieferung")["ende_am"] is None
    assert _finde(zp, "Einbau")["start_am"] == "2026-06-17"
    assert len(zp["abhaengigkeiten"]) == 1

    # Anderes Feld aendert nichts am Termin
    await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"liefertermin": "2026-07-01"})
    await client.patch(f"/api/bestellungen/{b.id}", headers=bh, json={"notiz": "x"})
    zp = (await client.get(_url(pid), headers=h)).json()
    assert _finde(zp, "Lieferung")["start_am"] == "2026-07-01"


@pytest.mark.asyncio
async def test_material_meilenstein_als_nachfolger_wird_nicht_verschoben(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin, liefertermin=date(2026, 6, 10))
    pid = await _projekt(client, h)
    await _element(client, h, pid, "schritt", "Planung", start_am="2026-06-01", ende_am="2026-06-05")
    zp = await _element(client, h, pid, "meilenstein", "Lieferung", bestellung_id=str(b.id))
    planung, ms = _finde(zp, "Planung"), _finde(zp, "Lieferung")
    await _verbinde(client, h, pid, planung, ms)
    zp = (await client.patch(_url(pid, f"/elemente/{planung['id']}"), headers=h,
                             json={"start_am": "2026-06-20", "ende_am": "2026-06-25"})).json()
    assert _finde(zp, "Lieferung")["start_am"] == "2026-06-10"  # Datum gehoert der Bestellung


@pytest.mark.asyncio
async def test_bestellung_create_und_read_liefertermin_und_pdf(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    b = await _bestellung(mandant, admin, liefertermin=date(2026, 6, 10))
    r = await client.get(f"/api/bestellungen/{b.id}", headers=h)
    assert r.json()["liefertermin"] == "2026-06-10"
    r = await client.get(f"/api/bestellungen/{b.id}/pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_bestellung_pdf_enthaelt_liefertermin_paar(monkeypatch):
    from app.services import pdf_service

    erfasst = {}

    def spion(pdf, mandant, empfaenger, *, paare, **kw):
        erfasst["paare"] = paare

    monkeypatch.setattr(pdf_service, "_beleg_rumpf", spion)
    monkeypatch.setattr(pdf_service, "_BelegPDF", lambda *a, **k: type("P", (), {"output": lambda self: b""})())
    b = Bestellung(bestellnummer="B-9", status="entwurf", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    b.liefertermin = date(2026, 6, 10)
    pdf_service.generate_bestellung_pdf(object(), b, [], None)
    assert ("Liefertermin", "10.06.2026") in erfasst["paare"]
    b.liefertermin = None
    pdf_service.generate_bestellung_pdf(object(), b, [], None)
    assert all(p[0] != "Liefertermin" for p in erfasst["paare"])


@pytest.mark.asyncio
async def test_bestellung_auswahl(client, make_mandant, make_user):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    alt = await _bestellung(mandant, admin, nummer="B-100", lieferant_name="Elektro Gross")
    neu = await _bestellung(mandant, admin, nummer="B-200", liefertermin=date(2026, 7, 1))
    await _bestellung(mandant, admin, nummer="B-300", geloescht_am=datetime.now(timezone.utc))
    fremd = await make_mandant()
    await _bestellung(fremd, await make_user(mandant=fremd, role="mandant_admin"), nummer="B-400")
    pid = await _projekt(client, h)

    body = (await client.get(_url(pid, "/auswahl/bestellungen"), headers=h)).json()
    assert [x["id"] for x in body] == [str(neu.id), str(alt.id)]
    assert body[0]["liefertermin"] == "2026-07-01"
    assert body[1]["lieferant_name"] == "Elektro Gross"
    assert set(body[0]) == {"id", "bestellnummer", "status", "liefertermin", "lieferant_name"}
    assert [x["id"] for x in (await client.get(_url(pid, "/auswahl/bestellungen?q=B-1"), headers=h)).json()] == [str(alt.id)]
    assert len((await client.get(_url(pid, "/auswahl/bestellungen?limit=1"), headers=h)).json()) == 1


# --- Fremdgewerk / Partnerportal -------------------------------------------


@pytest.mark.asyncio
async def test_partner_verknuepfen_regeln(client, make_mandant, make_user, make_partner):
    mandant, _, h = await _admin(client, make_mandant, make_user)
    partner = await make_partner(mandant=mandant, name="Elektro Blitz")
    inaktiv = await make_partner(mandant=mandant, name="Weg", aktiv=False)
    fremd = await make_partner(mandant=await make_mandant(), name="Fremd")
    pid = await _projekt(client, h)

    zp = await _element(client, h, pid, "schritt", "Elektro", partner_id=str(partner.id))
    assert _finde(zp, "Elektro")["partner"] == {"id": str(partner.id), "name": "Elektro Blitz"}
    for p in (inaktiv, fremd):
        r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "schritt", "titel": "X", "partner_id": str(p.id)})
        assert r.status_code == 400
    r = await client.post(_url(pid, "/elemente"), headers=h, json={"typ": "meilenstein", "titel": "X", "partner_id": str(partner.id)})
    assert r.status_code == 400
    zp = (await client.patch(_url(pid, f"/elemente/{_finde(zp, 'Elektro')['id']}"), headers=h, json={"partner_id": None})).json()
    assert _finde(zp, "Elektro")["partner"] is None


@pytest.mark.asyncio
async def test_partnerportal_zeitplan_sieht_nur_eigene_schritte(client, make_mandant, make_user, make_partner, make_kunde, make_vorgang):
    mandant, admin, h = await _admin(client, make_mandant, make_user)
    pa = await make_partner(mandant=mandant, name="A")
    pb = await make_partner(mandant=mandant, name="B")
    await _make_zugang(mandant, pa, email="a@p.example.de")
    await _make_zugang(mandant, pb, email="b@p.example.de")
    heute = date.today()

    pid = await _projekt(client, h, "Neubau Muster")
    zp = await _element(client, h, pid, "phase", "Rohbau")
    phase = _finde(zp, "Rohbau")
    d = lambda n: (heute + timedelta(days=n)).isoformat()  # noqa: E731
    await _element(client, h, pid, "schritt", "Spaeter", start_am=d(10), ende_am=d(12), partner_id=str(pa.id), phase_id=phase["id"], zugewiesen_an=str(admin.id))
    await _element(client, h, pid, "schritt", "Frueher", start_am=d(1), ende_am=d(3), partner_id=str(pa.id))
    await _element(client, h, pid, "schritt", "OhneDatum", partner_id=str(pa.id))
    await _element(client, h, pid, "schritt", "Alt", start_am=d(-60), ende_am=d(-40), partner_id=str(pa.id))
    await _element(client, h, pid, "schritt", "Grenze", start_am=d(-35), ende_am=d(-30), partner_id=str(pa.id))
    await _element(client, h, pid, "schritt", "FuerB", start_am=d(1), ende_am=d(2), partner_id=str(pb.id))
    await _element(client, h, pid, "schritt", "Intern", start_am=d(1), ende_am=d(2))
    await _element(client, h, pid, "meilenstein", "Meilenstein", start_am=d(1))
    kunde = await make_kunde(mandant=mandant)
    v = await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")
    await _element(client, h, pid, "schritt", "Erledigt", start_am=d(2), ende_am=d(4), partner_id=str(pa.id), vorgang_id=str(v.id))
    # geloeschtes Element + archiviertes/geloeschtes Projekt
    zp = await _element(client, h, pid, "schritt", "Geloescht", start_am=d(1), ende_am=d(2), partner_id=str(pa.id))
    await client.delete(_url(pid, f"/elemente/{_finde(zp, 'Geloescht')['id']}"), headers=h)
    pid_arch = await _projekt(client, h, "Archiv")
    await _element(client, h, pid_arch, "schritt", "InArchiv", start_am=d(1), ende_am=d(2), partner_id=str(pa.id))
    await client.patch(f"/api/projekte/{pid_arch}", headers=h, json={"archiviert": True})

    tok_a = (await _partner_login(client, "a@p.example.de", "partner-pw-123"))["access_token"]
    r = await client.get("/api/partnerportal/zeitplan", headers=auth_headers(tok_a))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["titel"] for x in body] == ["Grenze", "Frueher", "Erledigt", "Spaeter", "OhneDatum"]
    spaeter = next(x for x in body if x["titel"] == "Spaeter")
    assert set(spaeter) == {"id", "titel", "projekt_name", "phase_titel", "start_am", "ende_am", "fortschritt", "erledigt"}
    assert spaeter["projekt_name"] == "Neubau Muster" and spaeter["phase_titel"] == "Rohbau"
    erledigt = next(x for x in body if x["titel"] == "Erledigt")
    assert erledigt["erledigt"] is True and erledigt["fortschritt"] == 100
    assert next(x for x in body if x["titel"] == "Frueher")["phase_titel"] is None

    tok_b = (await _partner_login(client, "b@p.example.de", "partner-pw-123"))["access_token"]
    body_b = (await client.get("/api/partnerportal/zeitplan", headers=auth_headers(tok_b))).json()
    assert [x["titel"] for x in body_b] == ["FuerB"]

    # Fremder Mandant: Partner mit eigenem Zugang sieht nichts
    m2 = await make_mandant()
    p2 = await make_partner(mandant=m2)
    await _make_zugang(m2, p2, email="c@p.example.de")
    tok_c = (await _partner_login(client, "c@p.example.de", "partner-pw-123"))["access_token"]
    assert (await client.get("/api/partnerportal/zeitplan", headers=auth_headers(tok_c))).json() == []

    # Auth: ohne Token / mit internem Token
    assert (await client.get("/api/partnerportal/zeitplan")).status_code == 401
    assert (await client.get("/api/partnerportal/zeitplan", headers=h)).status_code == 401
    # read-only
    assert (await client.post("/api/partnerportal/zeitplan", headers=auth_headers(tok_a), json={})).status_code == 405


@pytest.mark.asyncio
async def test_zeitplan_get_hat_neue_felder_standardmaessig_leer(client, make_mandant, make_user):
    _, _, h = await _admin(client, make_mandant, make_user)
    pid = await _projekt(client, h)
    zp = await _element(client, h, pid, "schritt", "S")
    el = _finde(zp, "S")
    assert (el["vorgang"], el["termine"], el["bestellung"], el["datum_gesperrt"], el["partner"]) == (None, [], None, False, None)
