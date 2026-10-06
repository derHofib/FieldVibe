"""Scope fuer "Zeiten buchen" und "Abwesenheiten verwalten": Die Account-Typ-Flags bleiben
Voraussetzung, ein mitarbeiterverwaltung-Recht begrenzt zusaetzlich die Reichweite
(zuweisung_service.darf_fuer_mitarbeiter_handeln / mitarbeiter_im_handlungsbereich)."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.arbeitszeit import ArbeitszeitSoll
from app.models.organigramm import OrgEinheit, Position, PositionBesetzung
from app.models.user import User
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _typ(session, mandant, name, *, flags: bool, mv_scope: str | None):
    typ = AccountTyp(
        mandant_id=mandant.id,
        name=name,
        darf_zeiten_buchen=flags,
        darf_abwesenheiten_verwalten=flags,
    )
    session.add(typ)
    await session.flush()
    rechte = [("vorgaenge", a, "mandant") for a in ("sehen", "erstellen", "bearbeiten")]
    if mv_scope is not None:
        rechte.append(("mitarbeiterverwaltung", "bearbeiten", mv_scope))
    for bereich, aktion, scope in rechte:
        session.add(
            AccountTypRecht(
                mandant_id=mandant.id, account_typ_id=typ.id, bereich=bereich,
                aktion=aktion, erlaubt=True, scope=scope,
            )
        )
    await session.flush()
    return typ


async def _person(session, mandant, name, *, flags=False, mv_scope=None, parent=None, einheit=None):
    typ = await _typ(session, mandant, f"Typ {name}", flags=flags, mv_scope=mv_scope)
    position = Position(
        mandant_id=mandant.id,
        titel=name,
        parent_id=parent.id if parent else None,
        org_einheit_id=einheit.id if einheit else None,
        account_typ_id=typ.id,
        typ="linie",
    )
    session.add(position)
    user = User(
        mandant_id=mandant.id,
        email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.de",
        password_hash=hash_password(PW),
        role="custom",
        name=name,
    )
    session.add(user)
    await session.flush()
    session.add(
        ArbeitszeitSoll(
            mandant_id=mandant.id, user_id=user.id, gueltig_ab=date(2026, 1, 1),
            stunden_mo=8, stunden_di=8, stunden_mi=8, stunden_do=8, stunden_fr=8, stunden_sa=0, stunden_so=0,
        )
    )
    session.add(
        PositionBesetzung(
            mandant_id=mandant.id, position_id=position.id, user_id=user.id,
            gueltig_von=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await session.flush()
    return position, user


@pytest.fixture
async def org(make_mandant, make_kunde, make_vorgang, client):
    """Bereichsleiter -> Teamleiter A (A1, A2), Teamleiter B (B1); Ohne-MV = Flag ohne
    mitarbeiterverwaltung-Recht; Admin = mandant_admin."""
    mandant = await make_mandant()
    async with system_session() as session:
        bereich = OrgEinheit(mandant_id=mandant.id, name="Service", typ="bereich")
        session.add(bereich)
        await session.flush()
        team_a = OrgEinheit(mandant_id=mandant.id, name="Team A", typ="team", parent_id=bereich.id)
        team_b = OrgEinheit(mandant_id=mandant.id, name="Team B", typ="team", parent_id=bereich.id)
        session.add_all([team_a, team_b])
        await session.flush()
        bl_pos, bl = await _person(session, mandant, "Bereichsleiter", flags=True, mv_scope="bereich", einheit=bereich)
        tla_pos, tla = await _person(
            session, mandant, "Teamleiter A", flags=True, mv_scope="teilbaum", parent=bl_pos, einheit=team_a
        )
        tlb_pos, tlb = await _person(
            session, mandant, "Teamleiter B", flags=True, mv_scope="teilbaum", parent=bl_pos, einheit=team_b
        )
        _, a1 = await _person(session, mandant, "Techniker A1", parent=tla_pos, einheit=team_a)
        _, a2 = await _person(session, mandant, "Techniker A2", parent=tla_pos, einheit=team_a)
        _, b1 = await _person(session, mandant, "Techniker B1", parent=tlb_pos, einheit=team_b)
        _, ohne = await _person(session, mandant, "Ohne MV", flags=True)
        admin = User(
            mandant_id=mandant.id, email=f"admin-{uuid.uuid4().hex[:6]}@example.de",
            password_hash=hash_password(PW), role="mandant_admin", name="Admin",
        )
        session.add(admin)
        await session.flush()
        session.add(
            ArbeitszeitSoll(
                mandant_id=mandant.id, user_id=admin.id, gueltig_ab=date(2026, 1, 1),
                stunden_mo=8, stunden_di=8, stunden_mi=8, stunden_do=8, stunden_fr=8, stunden_sa=0, stunden_so=0,
            )
        )
        await session.flush()
        nutzer = {
            "bl": bl, "tla": tla, "tlb": tlb, "a1": a1, "a2": a2, "b1": b1, "ohne": ohne, "admin": admin,
        }
        ids = {k: u.id for k, u in nutzer.items()}
        emails = {k: u.email for k, u in nutzer.items()}
    headers = {k: auth_headers(await login(client, e, PW)) for k, e in emails.items()}
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    return {"mandant": mandant, "ids": ids, "headers": headers, "vorgang": vorgang}


_zaehler = iter(range(1000))


async def _antrag(client, org, wer: str, fuer: str | None = None) -> str:
    """Antrag eines Nutzers (je Aufruf eigene Woche, damit nichts kollidiert)."""
    montag = date(2027, 1, 4) + timedelta(weeks=next(_zaehler))
    body = {"art": "urlaub", "von": montag.isoformat(), "bis": (montag + timedelta(days=1)).isoformat()}
    if fuer is not None:
        body["user_id"] = str(org["ids"][fuer])
    resp = await client.post("/api/abwesenheiten", headers=org["headers"][wer], json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _offener_antrag(client, org, wer: str) -> str:
    """Antrag von `wer`, selbst gestellt; bleibt offen (Selbstgenehmigung nur mit Ausnahme)."""
    antrag = await _antrag(client, org, wer)
    assert antrag["status"] == "offen"
    return antrag["id"]


async def _genehmigen(client, org, wer: str, antrag_id: str):
    return await client.post(f"/api/abwesenheiten/{antrag_id}/genehmigen", headers=org["headers"][wer])


# --- Abwesenheiten -------------------------------------------------------


async def test_teamleiter_genehmigt_eigenes_team_nicht_fremdes_nicht_sich_selbst(client, org):
    a1 = await _offener_antrag(client, org, "a1")
    b1 = await _offener_antrag(client, org, "b1")
    tla = await _offener_antrag(client, org, "tla")
    assert (await _genehmigen(client, org, "tla", a1)).status_code == 200
    assert (await _genehmigen(client, org, "tla", b1)).status_code == 403
    assert (await _genehmigen(client, org, "tla", tla)).status_code == 403
    ablehnen = await client.post(f"/api/abwesenheiten/{b1}/ablehnen", headers=org["headers"]["tla"])
    assert ablehnen.status_code == 403


async def test_bereichsleiter_genehmigt_teamleiter_und_mitarbeiter(client, org):
    tla = await _offener_antrag(client, org, "tla")
    a1 = await _offener_antrag(client, org, "a1")
    b1 = await _offener_antrag(client, org, "b1")
    assert (await _genehmigen(client, org, "bl", tla)).status_code == 200
    assert (await _genehmigen(client, org, "bl", a1)).status_code == 200
    assert (await _genehmigen(client, org, "bl", b1)).status_code == 200


async def test_teamleiter_eigener_antrag_wird_nicht_automatisch_genehmigt(client, org):
    assert (await _antrag(client, org, "tla"))["status"] == "offen"


async def test_teamleiter_traegt_nur_fuer_eigenes_team_ein(client, org):
    ok = await _antrag(client, org, "tla", fuer="a1")
    assert ok["status"] == "genehmigt"
    resp = await client.post(
        "/api/abwesenheiten",
        headers=org["headers"]["tla"],
        json={"art": "urlaub", "von": "2027-06-07", "bis": "2027-06-08", "user_id": str(org["ids"]["b1"])},
    )
    assert resp.status_code == 403


async def test_ohne_mitarbeiterverwaltung_bleibt_mandantweit(client, org):
    b1 = await _offener_antrag(client, org, "b1")
    tla = await _offener_antrag(client, org, "tla")
    assert (await _genehmigen(client, org, "ohne", b1)).status_code == 200
    assert (await _genehmigen(client, org, "ohne", tla)).status_code == 200
    eigener = await _antrag(client, org, "ohne")
    assert eigener["status"] == "genehmigt"  # altes Verhalten, keine Sperre ohne Scope-Recht


async def test_mandant_admin_darf_alles_auch_eigenen_antrag(client, org):
    admin_antrag = await _antrag(client, org, "admin")
    assert admin_antrag["status"] == "genehmigt"
    for wer in ("a1", "tla", "b1"):
        assert (await _genehmigen(client, org, "admin", await _offener_antrag(client, org, wer))).status_code == 200


async def test_offene_antraege_liste_gefiltert(client, org):
    await _offener_antrag(client, org, "a1")
    await _offener_antrag(client, org, "b1")
    await _offener_antrag(client, org, "tla")

    async def namen(wer):
        resp = await client.get(
            "/api/abwesenheiten", headers=org["headers"][wer], params={"alle": True, "nur_offene": True}
        )
        assert resp.status_code == 200, resp.text
        return {a["user_name"] for a in resp.json()}

    assert await namen("tla") == {"Techniker A1", "Teamleiter A"}
    assert await namen("bl") == {"Techniker A1", "Techniker B1", "Teamleiter A"}
    assert await namen("ohne") == {"Techniker A1", "Techniker B1", "Teamleiter A"}
    assert await namen("admin") == {"Techniker A1", "Techniker B1", "Teamleiter A"}
    fremd = await client.get(
        "/api/abwesenheiten",
        headers=org["headers"]["tla"],
        params={"alle": True, "user_id": str(org["ids"]["b1"])},
    )
    assert fremd.status_code == 403


async def test_kalender_und_urlaubskonto_gefiltert(client, org):
    for wer in ("a1", "b1"):
        antrag = await _offener_antrag(client, org, wer)
        assert (await _genehmigen(client, org, "admin", antrag)).status_code == 200
    kalender = await client.get(
        "/api/abwesenheiten/kalender",
        headers=org["headers"]["tla"],
        params={"von": "2027-01-01", "bis": "2027-12-31"},
    )
    assert {e["user_name"] for e in kalender.json()} == {"Techniker A1"}
    assert (
        await client.get(
            "/api/abwesenheiten/konto", headers=org["headers"]["tla"], params={"user_id": str(org["ids"]["a1"])}
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/abwesenheiten/konto", headers=org["headers"]["tla"], params={"user_id": str(org["ids"]["b1"])}
        )
    ).status_code == 403


async def test_anspruch_setzen_nur_im_bereich(client, org):
    body = {"tage": "30", "resturlaub_tage": "0"}
    pfad = lambda k: f"/api/abwesenheiten/anspruch/{org['ids'][k]}/2027"  # noqa: E731
    assert (await client.put(pfad("a1"), headers=org["headers"]["tla"], json=body)).status_code == 200
    assert (await client.put(pfad("b1"), headers=org["headers"]["tla"], json=body)).status_code == 403
    assert (await client.put(pfad("tla"), headers=org["headers"]["tla"], json=body)).status_code == 403
    assert (await client.put(pfad("tla"), headers=org["headers"]["bl"], json=body)).status_code == 200


async def test_soll_setzen_nur_im_bereich(client, org):
    body = {"gueltig_ab": "2027-01-01", "stunden_mo": 8, "stunden_di": 8, "stunden_mi": 8, "stunden_do": 8,
            "stunden_fr": 8, "stunden_sa": 0, "stunden_so": 0}
    pfad = lambda k: f"/api/arbeitszeit/soll/{org['ids'][k]}"  # noqa: E731
    assert (await client.put(pfad("a1"), headers=org["headers"]["tla"], json=body)).status_code == 200
    assert (await client.put(pfad("b1"), headers=org["headers"]["tla"], json=body)).status_code == 403
    assert (
        await client.get(
            "/api/arbeitszeit/saldo",
            headers=org["headers"]["tla"],
            params={"von": "2027-01-04", "bis": "2027-01-08", "user_id": str(org["ids"]["b1"])},
        )
    ).status_code == 403


async def test_selbstgenehmigung_erlaubt_wenn_sonst_niemand_freigeben_kann(client, make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        _, solo = await _person(session, mandant, "Solo", flags=True, mv_scope="teilbaum")
        email = solo.email
    headers = auth_headers(await login(client, email, PW))
    resp = await client.post(
        "/api/abwesenheiten", headers=headers, json={"art": "urlaub", "von": "2027-03-01", "bis": "2027-03-02"}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "genehmigt"


# --- Zeiten buchen ---------------------------------------------------------


async def _eintrag(org, key: str) -> uuid.UUID:
    async with system_session() as session:
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        e = Zeiterfassung(
            mandant_id=org["mandant"].id,
            vorgang_id=org["vorgang"].id,
            techniker_id=org["ids"][key],
            start_at=start,
            ende_at=start + timedelta(hours=1),
            kategorie="auftrag",
            taetigkeit="Erledigt",
            abrechenbar=True,
        )
        session.add(e)
        await session.flush()
        return e.id


def _manuell(org, key: str) -> dict:
    start = datetime.now(timezone.utc) - timedelta(hours=5)
    return {
        "start_at": start.isoformat(),
        "ende_at": (start + timedelta(hours=1)).isoformat(),
        "kategorie": "verwaltung",
        "techniker_id": str(org["ids"][key]),
    }


async def test_zeiten_nachtragen_nur_fuer_bereich(client, org):
    h = org["headers"]
    assert (await client.post("/api/zeiterfassung/manuell", headers=h["tla"], json=_manuell(org, "a1"))).status_code == 201
    assert (await client.post("/api/zeiterfassung/manuell", headers=h["tla"], json=_manuell(org, "b1"))).status_code == 403
    assert (await client.post("/api/zeiterfassung/manuell", headers=h["bl"], json=_manuell(org, "b1"))).status_code == 201
    assert (await client.post("/api/zeiterfassung/manuell", headers=h["ohne"], json=_manuell(org, "b1"))).status_code == 201


async def test_zeiten_buchen_vormerken_stornieren_nur_fuer_bereich(client, org):
    h = org["headers"]
    a1, b1, tla = await _eintrag(org, "a1"), await _eintrag(org, "b1"), await _eintrag(org, "tla")

    fremd = await client.post("/api/zeiterfassung/buchen", headers=h["tla"], json={"ids": [str(b1)]})
    assert fremd.status_code == 400 and "Zuständigkeitsbereich" in fremd.text
    assert (await client.post("/api/zeiterfassung/vormerken", headers=h["tla"], json={"ids": [str(b1)]})).status_code == 400
    # Alles oder nichts: ein Eintrag ausserhalb sperrt die ganze Auswahl.
    gemischt = await client.post("/api/zeiterfassung/buchen", headers=h["tla"], json={"ids": [str(a1), str(b1)]})
    assert gemischt.status_code == 400

    assert (await client.post("/api/zeiterfassung/buchen", headers=h["tla"], json={"ids": [str(a1), str(tla)]})).status_code == 200
    storno = {"ids": [str(b1)], "grund": "Korrektur"}
    assert (await client.post("/api/zeiterfassung/buchung-stornieren", headers=h["tla"], json=storno)).status_code == 400
    assert (await client.post("/api/zeiterfassung/buchen", headers=h["bl"], json={"ids": [str(b1)]})).status_code == 200
    assert (await client.post("/api/zeiterfassung/buchung-stornieren", headers=h["bl"], json=storno)).status_code == 200


async def test_fremde_zeit_bearbeiten_loeschen_verlauf_nur_fuer_bereich(client, org):
    h = org["headers"]
    a1, b1 = await _eintrag(org, "a1"), await _eintrag(org, "b1")
    assert (await client.get(f"/api/zeiterfassung/{a1}/verlauf", headers=h["tla"])).status_code == 200
    assert (await client.get(f"/api/zeiterfassung/{b1}/verlauf", headers=h["tla"])).status_code == 404
    patch = {"taetigkeit": "Neu", "grund": "Korrektur"}
    assert (await client.patch(f"/api/zeiterfassung/{b1}", headers=h["tla"], json=patch)).status_code == 404
    assert (await client.delete(f"/api/zeiterfassung/{b1}", headers=h["tla"], params={"grund": "x"})).status_code == 404
    assert (await client.delete(f"/api/zeiterfassung/{a1}", headers=h["tla"], params={"grund": "x"})).status_code == 204
