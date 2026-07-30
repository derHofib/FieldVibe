from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.services.scheduler_service import run_dauerauftraege_scheduler
from tests.conftest import auth_headers, login


def _ziele_stmt(dauerauftrag_id):
    return select(DauerauftragZiel).where(DauerauftragZiel.dauerauftrag_id == dauerauftrag_id)


async def _make_dauerauftrag_mit_ziel(
    *,
    mandant,
    kunde,
    titel: str = "Wöchentliche Reinigung",
    intervall_tage: int = 7,
    naechste_faelligkeit_am: date | None = None,
    anlage=None,
    offener_vorgang=None,
    **kwargs,
) -> tuple[Dauerauftrag, DauerauftragZiel]:
    """Testhelfer: legt einen Dauerauftrag mit genau einem Ziel direkt in der
    DB an -- die meisten bestehenden Tests brauchten vor der
    Mehrfach-Anlagen-Umstellung nur ein einzelnes Ziel und greifen jetzt
    hierauf zurueck, statt jedes Mal Auftrag+Ziel einzeln zu bauen."""
    modus = kwargs.pop("modus", "rollierend")
    toleranz_frueh_tage = kwargs.pop("toleranz_frueh_tage", None)
    toleranz_spaet_tage = kwargs.pop("toleranz_spaet_tage", None)
    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel=titel,
            abrechnungsart=kwargs.pop("abrechnungsart", "wartungsvertrag"),
            leistungstyp=kwargs.pop("leistungstyp", "wartung"),
            intervall_tage=intervall_tage,
            modus=modus,
            toleranz_frueh_tage=toleranz_frueh_tage,
            toleranz_spaet_tage=toleranz_spaet_tage,
        )
        session.add(auftrag)
        await session.flush()

        ziel = DauerauftragZiel(
            mandant_id=mandant.id,
            dauerauftrag_id=auftrag.id,
            anlage_id=anlage.id if anlage is not None else None,
            naechste_faelligkeit_am=naechste_faelligkeit_am or date.today(),
            offener_vorgang_id=offener_vorgang.id if offener_vorgang is not None else None,
        )
        session.add(ziel)
        await session.flush()
        await session.refresh(auftrag)
        await session.refresh(ziel)
        return auftrag, ziel


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
    assert body["anzahl_ziele"] == 1
    assert len(body["ziele"]) == 1
    assert body["ziele"][0]["anlage_id"] is None
    assert body["ziele"][0]["offener_vorgang_id"] is None
    assert body["naechste_faelligkeit_am"] == date.today().isoformat()

    get_resp = await client.get(f"/api/dauerauftraege/{body['id']}", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["vorgaenge"] == []


@pytest.mark.asyncio
async def test_create_dauerauftrag_mit_mehreren_anlagen(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    """Statt 100 einzelner Daueraufträge fuer 100 Anlagen soll ein Buendel
    mehrere Anlagen desselben Kunden gleichzeitig abdecken."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage1 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 1")
    anlage2 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 2")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_ids": [str(anlage1.id), str(anlage2.id)],
            "titel": "Gebündelte Wartung",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 30,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["anzahl_ziele"] == 2
    anlage_ids_im_buendel = {z["anlage_id"] for z in body["ziele"]}
    assert anlage_ids_im_buendel == {str(anlage1.id), str(anlage2.id)}


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
            "anlage_ids": [str(fremde_anlage.id)],
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
async def test_set_anlagen_fuegt_hinzu_und_entfernt(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage1 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 1")
    anlage2 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 2")
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_ids": [str(anlage1.id)],
            "titel": "Buendel",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 7,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    auftrag_id = create_resp.json()["id"]

    set_resp = await client.put(
        f"/api/dauerauftraege/{auftrag_id}/anlagen",
        headers=auth_headers(token),
        json={
            "anlage_ids": [str(anlage2.id)],
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["anzahl_ziele"] == 1
    assert body["ziele"][0]["anlage_id"] == str(anlage2.id)


@pytest.mark.asyncio
async def test_scheduler_erzeugt_vorgang_wenn_faellig(make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)

    auftrag, ziel = await _make_dauerauftrag_mit_ziel(
        mandant=mandant,
        kunde=kunde,
        naechste_faelligkeit_am=date.today() - timedelta(days=1),
    )

    ergebnis = await run_dauerauftraege_scheduler([mandant.id])
    assert ergebnis["vorgaenge_erstellt"] == 1

    async with system_session() as session:
        ziel_neu = await session.get(DauerauftragZiel, ziel.id)
        assert ziel_neu.offener_vorgang_id is not None

    # Ein zweiter Lauf legt keinen weiteren Vorgang an, solange der erste
    # noch offen ist.
    ergebnis2 = await run_dauerauftraege_scheduler([mandant.id])
    assert ergebnis2["vorgaenge_erstellt"] == 0


@pytest.mark.asyncio
async def test_scheduler_bearbeitet_ziele_eines_buendels_unabhaengig(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    """Ein Buendel mit zwei Anlagen: das Abschliessen des Vorgangs der einen
    Anlage darf den Zyklus der anderen Anlage nicht beeinflussen."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage1 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 1")
    anlage2 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 2")

    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel="Buendel-Wartung",
            abrechnungsart="wartungsvertrag",
            leistungstyp="wartung",
            intervall_tage=7,
        )
        session.add(auftrag)
        await session.flush()
        for anlage in (anlage1, anlage2):
            session.add(
                DauerauftragZiel(
                    mandant_id=mandant.id,
                    dauerauftrag_id=auftrag.id,
                    anlage_id=anlage.id,
                    naechste_faelligkeit_am=date.today() - timedelta(days=1),
                )
            )
        await session.flush()
        auftrag_id = auftrag.id

    ergebnis = await run_dauerauftraege_scheduler([mandant.id])
    assert ergebnis["vorgaenge_erstellt"] == 2

    token = await login(client, admin.email, "pw-123456")
    detail_resp = await client.get(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    ziele_body = detail_resp.json()["ziele"]
    ziel_anlage1 = next(z for z in ziele_body if z["anlage_id"] == str(anlage1.id))
    ziel_anlage2 = next(z for z in ziele_body if z["anlage_id"] == str(anlage2.id))
    vorgang1_id = ziel_anlage1["offener_vorgang_id"]
    vorgang2_id = ziel_anlage2["offener_vorgang_id"]
    assert vorgang1_id is not None and vorgang2_id is not None

    await client.patch(
        f"/api/vorgaenge/{vorgang1_id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )

    detail_resp2 = await client.get(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    ziele_body2 = detail_resp2.json()["ziele"]
    ziel_anlage1_neu = next(z for z in ziele_body2 if z["anlage_id"] == str(anlage1.id))
    ziel_anlage2_neu = next(z for z in ziele_body2 if z["anlage_id"] == str(anlage2.id))
    assert ziel_anlage1_neu["offener_vorgang_id"] is None
    assert ziel_anlage2_neu["offener_vorgang_id"] == vorgang2_id


@pytest.mark.asyncio
async def test_abschluss_erzeugten_vorgangs_schreibt_naechste_faelligkeit_fort(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    auftrag, _ziel = await _make_dauerauftrag_mit_ziel(mandant=mandant, kunde=kunde)
    auftrag_id = auftrag.id

    await run_dauerauftraege_scheduler([mandant.id])

    async with system_session() as session:
        ziel = (
            await session.execute(_ziele_stmt(auftrag_id))
        ).scalars().one()
        vorgang_id = ziel.offener_vorgang_id

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
    assert detail["ziele"][0]["offener_vorgang_id"] is None
    erwartete_faelligkeit = (abgeschlossen_am.date() + timedelta(days=7)).isoformat()
    assert detail["naechste_faelligkeit_am"] == erwartete_faelligkeit
    assert detail["ziele"][0]["naechste_faelligkeit_am"] == erwartete_faelligkeit
    assert len(detail["vorgaenge"]) == 1
    assert detail["vorgaenge"][0]["dauerauftrag_id"] == str(auftrag_id)


@pytest.mark.asyncio
async def test_feed_zeigt_dauerauftrag_kennzeichnung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    auftrag, _ziel = await _make_dauerauftrag_mit_ziel(mandant=mandant, kunde=kunde)

    await run_dauerauftraege_scheduler([mandant.id])

    token = await login(client, admin.email, "pw-123456")
    feed_resp = await client.get("/api/feed", headers=auth_headers(token))
    items = feed_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["dauerauftrag_id"] == str(auftrag.id)


@pytest.mark.asyncio
async def test_modus_fest_schreibt_faelligkeit_ab_geplantem_termin_fort(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    """modus="fest": die naechste Faelligkeit haengt am urspruenglich
    geplanten Termin, nicht am tatsaechlichen Abschlussdatum -- der
    Kalenderrhythmus bleibt fest, auch wenn frueher oder spaeter
    abgeschlossen wird."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    geplante_faelligkeit = date.today() - timedelta(days=3)

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    auftrag, _ziel = await _make_dauerauftrag_mit_ziel(
        mandant=mandant,
        kunde=kunde,
        titel="Feste Wartung",
        naechste_faelligkeit_am=geplante_faelligkeit,
        modus="fest",
        offener_vorgang=vorgang,
    )
    auftrag_id = auftrag.id

    token = await login(client, admin.email, "pw-123456")
    await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )

    detail_resp = await client.get(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    detail = detail_resp.json()
    assert detail["naechste_faelligkeit_am"] == (geplante_faelligkeit + timedelta(days=7)).isoformat()
    assert detail["ziele"][0]["offener_vorgang_id"] is None


@pytest.mark.asyncio
async def test_zu_frueher_abschluss_erzeugt_hinweis_event(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    geplante_faelligkeit = date.today() + timedelta(days=10)

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _make_dauerauftrag_mit_ziel(
        mandant=mandant,
        kunde=kunde,
        titel="Toleranz-Test frueh",
        naechste_faelligkeit_am=geplante_faelligkeit,
        toleranz_frueh_tage=3,
        offener_vorgang=vorgang,
    )

    token = await login(client, admin.email, "pw-123456")
    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert resp.status_code == 200

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    hinweise = [e for e in events_resp.json() if "vor der geplanten" in (e["body"] or "")]
    assert len(hinweise) == 1


@pytest.mark.asyncio
async def test_zu_spaeter_abschluss_erzeugt_hinweis_event(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    geplante_faelligkeit = date.today() - timedelta(days=10)

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _make_dauerauftrag_mit_ziel(
        mandant=mandant,
        kunde=kunde,
        titel="Toleranz-Test spaet",
        naechste_faelligkeit_am=geplante_faelligkeit,
        toleranz_spaet_tage=3,
        offener_vorgang=vorgang,
    )

    token = await login(client, admin.email, "pw-123456")
    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert resp.status_code == 200

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    hinweise = [e for e in events_resp.json() if "nach der geplanten" in (e["body"] or "")]
    assert len(hinweise) == 1


@pytest.mark.asyncio
async def test_innerhalb_toleranz_kein_hinweis_event(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _make_dauerauftrag_mit_ziel(
        mandant=mandant,
        kunde=kunde,
        titel="Innerhalb Toleranz",
        naechste_faelligkeit_am=date.today(),
        toleranz_frueh_tage=2,
        toleranz_spaet_tage=2,
        offener_vorgang=vorgang,
    )

    token = await login(client, admin.email, "pw-123456")
    await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    hinweise = [
        e
        for e in events_resp.json()
        if "geplanten" in (e["body"] or "")
    ]
    assert hinweise == []


@pytest.mark.asyncio
async def test_dauerauftrag_loeschen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    auftrag, _ziel = await _make_dauerauftrag_mit_ziel(
        mandant=mandant, kunde=kunde, titel="Zu loeschen", offener_vorgang=vorgang
    )
    auftrag_id = auftrag.id
    async with system_session() as session:
        v = await session.get(type(vorgang), vorgang.id)
        v.dauerauftrag_id = auftrag_id
        await session.flush()

    token = await login(client, admin.email, "pw-123456")
    delete_resp = await client.delete(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(token))
    assert get_resp.status_code == 404

    # Der Vorgang selbst bleibt bestehen, verliert nur die Rueckverknuepfung.
    vorgang_resp = await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    assert vorgang_resp.status_code == 200
    assert vorgang_resp.json()["dauerauftrag_id"] is None


@pytest.mark.asyncio
async def test_techniker_darf_dauerauftrag_nicht_loeschen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    admin_token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/dauerauftraege",
        headers=auth_headers(admin_token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Test",
            "abrechnungsart": "wartungsvertrag",
            "leistungstyp": "wartung",
            "intervall_tage": 7,
            "naechste_faelligkeit_am": date.today().isoformat(),
        },
    )
    auftrag_id = create_resp.json()["id"]

    techniker_token = await login(client, techniker.email, "pw-123456")
    resp = await client.delete(
        f"/api/dauerauftraege/{auftrag_id}", headers=auth_headers(techniker_token)
    )
    assert resp.status_code == 403
