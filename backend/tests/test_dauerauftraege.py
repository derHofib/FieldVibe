from datetime import date, datetime, timedelta

import pytest

from app.db.session import system_session
from app.models.dauerauftrag import Dauerauftrag
from app.services.scheduler_service import run_dauerauftraege_scheduler
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_dauerauftrag(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Monatliche Wartung",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 30,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["titel"] == "Monatliche Wartung"
    assert body["aktiv"] is True
    assert body["offener_vorgang_id"] is None

    get_resp = await client.get(f"/api/dauerauftraege/{body['id']}", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["vorgaenge"] == []


@pytest.mark.asyncio
async def test_techniker_darf_keinen_dauerauftrag_anlegen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Sollte scheitern",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 7,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_anlage_muss_zum_kunden_gehoeren(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anderer_kunde = await make_kunde(mandant=mandant, name="Anderer Kunde")
    fremde_anlage = await make_anlage(mandant=mandant, kunde=anderer_kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": str(fremde_anlage.id),
            "titel": "Sollte scheitern",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 7,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_techniker_sieht_nur_dauerauftraege_zugewiesener_kunden(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde_zugewiesen = await make_kunde(mandant=mandant, name="Zugewiesen")
    kunde_fremd = await make_kunde(mandant=mandant, name="Nicht zugewiesen")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde_zugewiesen, techniker=techniker)
    admin_token = await login(client, admin.email, "pw-123456")

    for kunde, titel in ((kunde_zugewiesen, "Sichtbar"), (kunde_fremd, "Nicht sichtbar")):
        await client.post(
            "/api/dauerauftraege",
            headers=auth_headers(admin_token),
            json={
                "kunde_id": str(kunde.id),
                "titel": titel,
                "abrechnungsart": "wartungsvertrag",
                "leistungstyp": "wartung",
                "intervall_tage": 7,
                "naechste_faelligkeit_am": date.today().isoformat(),
            },
        )

    techniker_token = await login(client, techniker.email, "pw-123456")
    resp = await client.get("/api/dauerauftraege", headers=auth_headers(techniker_token))
    assert [d["titel"] for d in resp.json()] == ["Sichtbar"]


@pytest.mark.asyncio
async def test_update_dauerauftrag_pause_und_intervall(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Test",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 7,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    dauerauftrag_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/dauerauftraege/{dauerauftrag_id}",
        headers=auth_headers(token),
        json={"aktiv": False, "intervall_tage": 14},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["aktiv"] is False
    assert update_resp.json()["intervall_tage"] == 14


@pytest.mark.asyncio
async def test_scheduler_erzeugt_vorgang_wenn_faellig(make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)

    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel="Wöchentliche Reinigung",
            abrechnungsart="wartungsvertrag",
            leistungstyp="wartung",
            intervall_tage=7,
            naechste_faelligkeit_am=date.today() - timedelta(days=1),
        )
        session.add(auftrag)
        await session.flush()
        auftrag_id = auftrag.id

    ergebnis = await run_dauerauftraege_scheduler([mandant.id])
    assert ergebnis["vorgaenge_erstellt"] == 1

    async with system_session() as session:
        auftrag = await session.get(Dauerauftrag, auftrag_id)
        assert auftrag.offener_vorgang_id is not None

    # Ein zweiter Lauf legt keinen weiteren Vorgang an, solange der erste
    # noch offen ist.
    ergebnis2 = await run_dauerauftraege_scheduler([mandant.id])
    assert ergebnis2["vorgaenge_erstellt"] == 0


@pytest.mark.asyncio
async def test_abschluss_erzeugten_vorgangs_schreibt_naechste_faelligkeit_fort(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel="Wöchentliche Reinigung",
            abrechnungsart="wartungsvertrag",
            leistungstyp="wartung",
            intervall_tage=7,
            naechste_faelligkeit_am=date.today(),
        )
        session.add(auftrag)
        await session.flush()
        auftrag_id = auftrag.id

    await run_dauerauftraege_scheduler([mandant.id])

    async with system_session() as session:
        auftrag = await session.get(Dauerauftrag, auftrag_id)
        vorgang_id = auftrag.offener_vorgang_id

    token = await login(client, admin.email, "pw-123456")
    patch_resp = await client.patch(
        f"/api/vorgaenge/{vorgang_id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen"},
    )
    assert patch_resp.status_code == 200
    abgeschlossen_am = datetime.fromisoformat(patch_resp.json()["abgeschlossen_am"])

    detail_resp = await client.get(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    detail = detail_resp.json()
    assert detail["offener_vorgang_id"] is None
    erwartete_faelligkeit = (abgeschlossen_am.date() + timedelta(days=7)).isoformat()
    assert detail["naechste_faelligkeit_am"] == erwartete_faelligkeit
    assert len(detail["vorgaenge"]) == 1
    assert detail["vorgaenge"][0]["dauerauftrag_id"] == str(auftrag_id)


@pytest.mark.asyncio
async def test_feed_zeigt_dauerauftrag_kennzeichnung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel="Wöchentliche Reinigung",
            abrechnungsart="wartungsvertrag",
            leistungstyp="wartung",
            intervall_tage=7,
            naechste_faelligkeit_am=date.today(),
        )
        session.add(auftrag)
        await session.flush()

    await run_dauerauftraege_scheduler([mandant.id])

    token = await login(client, admin.email, "pw-123456")
    feed_resp = await client.get("/api/feed", headers=auth_headers(token))
    items = feed_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["dauerauftrag_id"] == str(auftrag.id)
