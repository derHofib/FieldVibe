"""Endgueltiges Loeschen raeumt den Objektspeicher auf; Mandantenpraefix der Schluessel."""
import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session, tenant_session
from app.models.rechnung import Rechnung
from app.models.s3_loeschauftrag import S3Loeschauftrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.services import papierkorb_service, s3_aufraeumen_service, storage_service
from tests.conftest import auth_headers, login


def _liste(prefix: str) -> list[str]:
    antwort = storage_service._internal_client.list_objects_v2(Bucket=storage_service.BUCKET, Prefix=prefix)
    return [o["Key"] for o in antwort.get("Contents", [])]


async def _hintergrund_fertig() -> None:
    tasks = s3_aufraeumen_service.hintergrund_tasks()
    if tasks:
        await asyncio.gather(*tasks)


async def _vorgang_mit_dateien(mandant, kunde, *, titel: str, legacy: bool = False) -> tuple[Vorgang, list[str]]:
    async with system_session() as session:
        v = Vorgang(
            mandant_id=mandant.id, vorgangsnummer=f"V-{uuid.uuid4().hex[:6]}", kunde_id=kunde.id, titel=titel,
            abrechnungsart="aufwand", leistungstyp="stoerung",
            geloescht_am=datetime.now(timezone.utc),
        )
        session.add(v)
        await session.flush()
        keys = []
        for name in ("foto.jpg", "dokument.pdf", "unterschrift.png"):
            key = f"vorgaenge/{v.id}/{uuid.uuid4()}.{name.rsplit('.', 1)[1]}" if legacy else storage_service.new_object_key(mandant.id, v.id, name)
            await storage_service.upload_bytes(key, b"daten-" + name.encode(), "application/octet-stream")
            keys.append(key)
        thumb = keys[0].rsplit(".", 1)[0] + "_thumb.jpg"
        await storage_service.upload_bytes(thumb, b"thumb", "image/jpeg")
        keys.append(thumb)
        session.add(VorgangEvent(mandant_id=mandant.id, vorgang_id=v.id, event_type="foto", payload={"key": keys[0], "thumbnail_key": thumb}))
        return v, keys


@pytest.mark.asyncio
async def test_purge_loescht_objekte_nach_commit_und_nur_die_eigenen(client, make_mandant, make_user, make_kunde):
    a = await make_mandant("A")
    b = await make_mandant("B")
    operativ = await make_user(mandant=a, role="loesch_operativ", password="pw-123456")
    kunde_a, kunde_b = await make_kunde(mandant=a), await make_kunde(mandant=b)
    h = auth_headers(await login(client, operativ.email, "pw-123456"))

    v_neu, keys_neu = await _vorgang_mit_dateien(a, kunde_a, titel="neu")
    v_alt, keys_alt = await _vorgang_mit_dateien(a, kunde_a, titel="alt (Altschema ohne Mandantenpraefix)", legacy=True)
    v_b, keys_b = await _vorgang_mit_dateien(b, kunde_b, titel="fremd")
    v_bleibt, keys_bleibt = await _vorgang_mit_dateien(a, kunde_a, titel="bleibt")

    for v in (v_neu, v_alt):
        assert (await client.delete(f"/api/papierkorb/vorgang/{v.id}", headers=h)).status_code == 204
    await _hintergrund_fertig()

    for key in (*keys_neu, *keys_alt):
        assert _liste(key) == [], key
    for key in (*keys_b, *keys_bleibt):
        assert _liste(key) == [key], key  # fremde und nicht geloeschte Objekte bleiben
    async with system_session() as session:
        auftraege = (await session.execute(select(S3Loeschauftrag))).scalars().all()
    assert {x.status for x in auftraege} == {"erledigt"} and len(auftraege) == 4  # 2 Vorgaenge x (neues, altes Praefix)


@pytest.mark.asyncio
async def test_rollback_hinterlaesst_weder_auftrag_noch_objektverlust(make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    v, keys = await _vorgang_mit_dateien(mandant, kunde, titel="x")
    with pytest.raises(RuntimeError):
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            assert await papierkorb_service.purge(session, entity_typ="vorgang", entity_id=v.id)
            raise RuntimeError("nach dem Loeschen schlaegt etwas fehl")
    await _hintergrund_fertig()
    for key in keys:
        assert _liste(key) == [key]
    async with system_session() as session:
        assert await session.get(Vorgang, v.id) is not None
        assert (await session.execute(select(S3Loeschauftrag))).first() is None


@pytest.mark.asyncio
async def test_s3_fehler_wird_tolerant_protokolliert_und_wiederholt(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    ho = auth_headers(await login(client, operativ.email, "pw-123456"))
    v, keys = await _vorgang_mit_dateien(mandant, kunde, titel="x")

    async def kaputt(prefix):
        raise RuntimeError("S3 nicht erreichbar")

    monkeypatch.setattr(storage_service, "delete_prefix", kaputt)
    # Das Loeschen in der Datenbank gelingt trotz S3-Ausfall (kein 5xx).
    assert (await client.delete(f"/api/papierkorb/vorgang/{v.id}", headers=ho)).status_code == 204
    await _hintergrund_fertig()
    for key in keys:
        assert _liste(key) == [key]  # noch da

    liste = (await client.get("/api/aufbewahrung/s3-loeschauftraege", headers=h)).json()
    assert len(liste) == 2 and all(x["status"] == "offen" and x["versuche"] == 1 for x in liste)
    assert "nicht erreichbar" in liste[0]["letzter_fehler"]

    # Backoff: sofort erneut ist nichts faellig; nach Ablauf der Wartezeit klappt es mit funktionierendem S3.
    assert await s3_aufraeumen_service.verarbeite() == {"erledigt": 0, "fehlgeschlagen": 0}
    monkeypatch.undo()
    async with system_session() as session:
        for a in (await session.execute(select(S3Loeschauftrag))).scalars():
            a.naechster_versuch_am = datetime.now(timezone.utc)
    assert await s3_aufraeumen_service.verarbeite() == {"erledigt": 2, "fehlgeschlagen": 0}
    for key in keys:
        assert _liste(key) == []
    assert (await client.get("/api/aufbewahrung/s3-loeschauftraege", headers=h)).json() == []


@pytest.mark.asyncio
async def test_nach_max_versuchen_steht_der_auftrag_auf_fehler(make_mandant, make_kunde, monkeypatch):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    v, _ = await _vorgang_mit_dateien(mandant, kunde, titel="x")

    async def kaputt(prefix):
        raise RuntimeError("AccessDenied (Object Lock)")

    monkeypatch.setattr(storage_service, "delete_prefix", kaputt)
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        await papierkorb_service.purge(session, entity_typ="vorgang", entity_id=v.id)
    await _hintergrund_fertig()
    for _ in range(s3_aufraeumen_service.MAX_VERSUCHE):
        async with system_session() as session:
            for a in (await session.execute(select(S3Loeschauftrag).where(S3Loeschauftrag.status == "offen"))).scalars():
                a.naechster_versuch_am = datetime.now(timezone.utc)
        await s3_aufraeumen_service.verarbeite()
    async with system_session() as session:
        status = {a.status for a in (await session.execute(select(S3Loeschauftrag))).scalars()}
    assert status == {"fehler"}


@pytest.mark.asyncio
async def test_rechnungsarchiv_wird_nach_ablauf_der_frist_mit_entfernt(make_mandant, make_user, make_kunde, client):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    r = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "10"})).json()
    await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})
    async with system_session() as session:
        pdf_key = (await session.get(Rechnung, uuid.UUID(r["id"]))).pdf_object_key
    assert pdf_key.startswith(f"mandanten/{mandant.id}/rechnungen/{r['id']}/")
    assert _liste(pdf_key) == [pdf_key]

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        await papierkorb_service.soft_delete(session, entity_typ="rechnung", entity_id=uuid.UUID(r["id"]), actor_user_id=admin.id)
    with pytest.raises(papierkorb_service.GobdLoeschsperre):
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            await papierkorb_service.purge(session, entity_typ="rechnung", entity_id=uuid.UUID(r["id"]))
    assert _liste(pdf_key) == [pdf_key]  # gesperrt: Objekt bleibt

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        await papierkorb_service.purge(
            session, entity_typ="rechnung", entity_id=uuid.UUID(r["id"]), heute=date(date.today().year + 9, 1, 1)
        )
    await _hintergrund_fertig()
    assert _liste(pdf_key) == []


@pytest.mark.asyncio
async def test_aufraeumen_faellt_ohne_recht_zum_auflisten_von_versionen_auf_den_einfachen_weg_zurueck(monkeypatch):
    """Aeltere MinIO-Service-Accounts haben nur ListBucket/DeleteObject."""
    from botocore.exceptions import ClientError

    prefix = f"mandanten/{uuid.uuid4()}/vorgaenge/{uuid.uuid4()}/"
    for i in range(3):
        await storage_service.upload_bytes(f"{prefix}{i}.bin", b"x", "application/octet-stream")
    original = storage_service._internal_client.get_paginator

    def ohne_versionen(name):
        if name == "list_object_versions":
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nein"}}, "ListObjectVersions")
        return original(name)

    monkeypatch.setattr(storage_service._internal_client, "get_paginator", ohne_versionen)
    assert await storage_service.delete_prefix(prefix) == 3
    assert _liste(prefix) == []


@pytest.mark.asyncio
async def test_zu_allgemeine_praefixe_werden_abgelehnt():
    for prefix in ("", "/", "mandanten/", "vorgaenge/", "mandanten", "vorgaenge/abc", "/mandanten/x/"):
        with pytest.raises(ValueError):
            await storage_service.delete_prefix(prefix)


def test_neue_schluessel_tragen_den_mandantenpraefix_und_sind_getrennt():
    a, b = uuid.uuid4(), uuid.uuid4()
    entitaet = uuid.uuid4()
    schluessel = [
        storage_service.new_object_key(a, entitaet, "x.jpg"),
        storage_service.new_kunde_logo_key(a, entitaet, "x.png"),
        storage_service.new_mandant_logo_key(a, "x.png"),
        storage_service.new_board_hintergrund_key(a, entitaet, "x.png"),
        storage_service.new_board_anhang_key(a, entitaet, "x.pdf"),
        storage_service.new_rechnung_pdf_key(a, entitaet),
        storage_service.new_rechnung_xml_key(a, entitaet),
        storage_service.new_eingangsrechnung_beleg_key(a, entitaet, "x.pdf"),
        storage_service.new_eingangsrechnung_xml_key(a, entitaet),
        storage_service.new_mail_attachment_key(a, entitaet, "x.txt"),
        storage_service.new_partner_nachweis_key(a, entitaet, "x.pdf"),
        storage_service.new_plan_symbol_key(a, "x.png"),
        storage_service.new_fehlerbericht_screenshot_key(a, entitaet, "s"),
        storage_service.new_import_quelle_key(a, entitaet),
        storage_service.new_import_fehlerbericht_key(a, entitaet),
    ]
    for key in schluessel:
        assert key.startswith(f"mandanten/{a}/"), key
        assert storage_service.key_gehoert_zu_mandant(key, a) is True
        assert storage_service.key_gehoert_zu_mandant(key, b) is False  # nie fuer einen anderen Mandanten aufloesbar
    # Gleiche Entitaets-ID, anderer Mandant -> anderer Schluessel.
    assert storage_service.new_rechnung_pdf_key(b, entitaet).split("/")[1] == str(b)
    # Altobjekte: aus dem Schluessel nicht entscheidbar, Zuordnung nur ueber die DB (RLS).
    assert storage_service.key_gehoert_zu_mandant(f"vorgaenge/{entitaet}/x.jpg", a) is None
    assert storage_service.mandant_prefix(a) == f"mandanten/{a}/"


@pytest.mark.asyncio
async def test_fremder_mandant_loest_keinen_schluessel_auf_und_altobjekte_bleiben_lesbar(client, make_mandant, make_user, make_kunde):
    a = await make_mandant("A")
    b = await make_mandant("B")
    admin_a = await make_user(mandant=a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=b, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=a)
    ha = auth_headers(await login(client, admin_a.email, "pw-123456"))
    hb = auth_headers(await login(client, admin_b.email, "pw-123456"))
    r = (await client.post("/api/rechnungen", headers=ha, json={"kunde_id": str(kunde.id), "betrag_netto": "10"})).json()
    await client.patch(f"/api/rechnungen/{r['id']}", headers=ha, json={"status": "versendet"})
    assert (await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=ha)).content.startswith(b"%PDF")
    assert (await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=hb)).status_code == 404
    assert (await client.get(f"/api/rechnungen/{r['id']}/xml", headers=hb)).status_code == 404

    # Altobjekt (Schluessel im frueheren Schema ohne Mandantenpraefix) ist weiter lesbar.
    async with system_session() as session:
        rechnung = await session.get(Rechnung, uuid.UUID(r["id"]))
        alt_key = f"rechnungen/{rechnung.id}/versendet-{uuid.uuid4()}.pdf"
        inhalt = await storage_service.download_bytes(rechnung.pdf_object_key)
        await storage_service.upload_bytes(alt_key, inhalt, "application/pdf")
        from sqlalchemy import text

        await session.execute(text("ALTER TABLE rechnungen DISABLE TRIGGER trg_rechnungen_festschreibung"))
        await session.execute(text("UPDATE rechnungen SET pdf_object_key = :k WHERE id = :i"), {"k": alt_key, "i": rechnung.id})
        await session.execute(text("ALTER TABLE rechnungen ENABLE TRIGGER trg_rechnungen_festschreibung"))
    assert (await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=ha)).content.startswith(b"%PDF")
    assert (await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=hb)).status_code == 404
