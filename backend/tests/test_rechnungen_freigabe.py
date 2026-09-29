"""Stunden freigeben bei Loeschen/Storno einer Rechnung, Wiederherstellen aus
dem Papierkorb und SVS-Zeit (lv_position_id) als gesperrte Rechnungsgrundlage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import system_session, tenant_session
from app.models.rechnung import RechnungPosition
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.models.zeiterfassung_aenderung import ZeiterfassungAenderung
from app.services import rechnung_service
from tests.conftest import auth_headers, login
from tests.test_rechnungen_sammelrechnung import _daten_zwei_vorgaenge, _setup, _svs, _zeit


async def _sammelrechnung(client, token, kunde, *vorgaenge):
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgaenge": [{"vorgang_id": str(v.id)} for v in vorgaenge]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _zeilen(*ids):
    async with system_session() as session:
        return [await session.get(Zeiterfassung, i) for i in ids]


async def _abrechenbar(client, token, kunde):
    resp = await client.get(f"/api/rechnungen/abrechenbare-vorgaenge?kunde_id={kunde.id}", headers=auth_headers(token))
    assert resp.status_code == 200
    return {v["vorgang_id"] for v in resp.json()}


@pytest.mark.asyncio
async def test_entwurf_loeschen_gibt_stunden_frei_und_restore_sperrt_wieder(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    ids = await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    rechnung = await _sammelrechnung(client, token, kunde, va, vb)
    assert all(e.buchungsstatus == "abgerechnet" for e in await _zeilen(*ids))
    assert await _abrechenbar(client, token, kunde) == set()

    resp = await client.delete(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))
    assert resp.status_code == 204, resp.text

    for e in await _zeilen(*ids):
        assert e.buchungsstatus == "gebucht"
        # Verweis bleibt fuers Wiederherstellen erhalten
        assert str(e.abgerechnet_rechnung_id) == rechnung["id"]
    assert await _abrechenbar(client, token, kunde) == {str(va.id), str(vb.id)}

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_token = await login(client, operativ.email, "pw-123456")
    resp = await client.post(
        f"/api/papierkorb/rechnung/{rechnung['id']}/wiederherstellen", headers=auth_headers(op_token)
    )
    assert resp.status_code in (200, 204), resp.text

    for e in await _zeilen(*ids):
        assert e.buchungsstatus == "abgerechnet"
        assert str(e.abgerechnet_rechnung_id) == rechnung["id"]
    assert await _abrechenbar(client, token, kunde) == set()
    async with system_session() as session:
        aktionen = (
            await session.execute(
                select(ZeiterfassungAenderung.aktion).where(ZeiterfassungAenderung.zeiterfassung_id == ids[0])
            )
        ).scalars().all()
    assert aktionen.count("abgerechnet") == 2
    assert aktionen.count("abrechnung_zurueckgesetzt") == 1


@pytest.mark.asyncio
async def test_restore_ueberspringt_zwischenzeitlich_neu_abgerechnete_zeile(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    a, b_ohne, b_svs = await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    alt = await _sammelrechnung(client, token, kunde, va, vb)
    await client.delete(f"/api/rechnungen/{alt['id']}", headers=auth_headers(token))

    # Neue Rechnung nur fuer Vorgang A: sperrt Zeile a erneut
    neu = await _sammelrechnung(client, token, kunde, va)
    (ea,) = await _zeilen(a)
    assert str(ea.abgerechnet_rechnung_id) == neu["id"]

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_token = await login(client, operativ.email, "pw-123456")
    resp = await client.post(f"/api/papierkorb/rechnung/{alt['id']}/wiederherstellen", headers=auth_headers(op_token))
    assert resp.status_code in (200, 204), resp.text

    ea, eb_ohne, eb_svs = await _zeilen(a, b_ohne, b_svs)
    assert ea.buchungsstatus == "abgerechnet" and str(ea.abgerechnet_rechnung_id) == neu["id"]
    assert eb_ohne.buchungsstatus == "abgerechnet" and str(eb_ohne.abgerechnet_rechnung_id) == alt["id"]
    assert eb_svs.buchungsstatus == "abgerechnet" and str(eb_svs.abgerechnet_rechnung_id) == alt["id"]


@pytest.mark.asyncio
async def test_purge_geloeschter_rechnung_loest_verweis(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    a, b_ohne, b_svs = await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    rechnung = await _sammelrechnung(client, token, kunde, va, vb)
    await client.delete(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_token = await login(client, operativ.email, "pw-123456")
    resp = await client.delete(f"/api/papierkorb/rechnung/{rechnung['id']}", headers=auth_headers(op_token))
    assert resp.status_code == 204, resp.text

    for e in await _zeilen(a, b_ohne, b_svs):
        assert e.buchungsstatus == "gebucht"
        assert e.abgerechnet_rechnung_id is None


@pytest.mark.asyncio
async def test_storno_gibt_stunden_frei_und_schreibt_events_an_alle_vorgaenge(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    ids = await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    rechnung = await _sammelrechnung(client, token, kunde, va, vb)
    # pdf_service._positionen_tabelle maskiert den Gedankenstrich der
    # Sammelrechnungs-Beschreibungen nicht (bekannter Fund, nicht Teil dieses
    # Tests) -- fuer den Versand hier ASCII setzen.
    async with system_session() as session:
        for p in (
            await session.execute(select(RechnungPosition).where(RechnungPosition.rechnung_id == UUID(rechnung["id"])))
        ).scalars():
            p.beschreibung = p.beschreibung.replace("\u2013", "-")
    resp = await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    storno = resp.json()

    for e in await _zeilen(*ids):
        assert e.buchungsstatus == "gebucht"
        assert e.abgerechnet_rechnung_id is None
    # Die Stornorechnung selbst sperrt nichts und traegt keine Quelle/Vorgang
    assert all(p["quelle"] is None and p["vorgang_id"] is None for p in storno["positionen"])
    assert await _abrechenbar(client, token, kunde) == {str(va.id), str(vb.id)}

    async with system_session() as session:
        events = (
            await session.execute(
                select(VorgangEvent.vorgang_id).where(
                    VorgangEvent.event_type == "rechnung_status",
                    VorgangEvent.body.like("%storniert durch%"),
                )
            )
        ).scalars().all()
    assert set(events) == {va.id, vb.id}


@pytest.mark.asyncio
async def test_svs_zeit_wird_gesperrt_und_gezielt_freigegeben(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        svs1 = await _svs(session, mandant)
        svs2 = await _svs(session, mandant)
        s1 = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=1, lv_position_id=svs1.id)
        s2 = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2, lv_position_id=svs2.id)
        s_b = await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=4, lv_position_id=svs1.id)
        ohne = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=8)

    rechnung = await _sammelrechnung(client, token, kunde, va, vb)
    for e in await _zeilen(s1, s2, s_b, ohne):
        assert e.buchungsstatus == "abgerechnet"
    leistung_pos = [p for p in rechnung["positionen"] if p["quelle"] == "leistung"]
    assert {p["lv_position_id"] for p in leistung_pos} == {str(svs1.id), str(svs2.id)}

    # "leistung" fuer svs1 an Vorgang A entfernen: nur s1 wird frei
    pos = next(
        p for p in leistung_pos if p["lv_position_id"] == str(svs1.id) and p["vorgang_id"] == str(va.id)
    )
    resp = await client.delete(f"/api/rechnungen/{rechnung['id']}/positionen/{pos['id']}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    e1, e2, eb, eo = await _zeilen(s1, s2, s_b, ohne)
    assert e1.buchungsstatus == "gebucht" and e1.abgerechnet_rechnung_id is None
    assert e2.buchungsstatus == "abgerechnet"
    assert eb.buchungsstatus == "abgerechnet"
    assert eo.buchungsstatus == "abgerechnet"


@pytest.mark.asyncio
async def test_zeit_und_leistung_teilen_sich_keine_zeilen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        svs = await _svs(session, mandant)
        svs_zeile = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=1, lv_position_id=svs.id)
        ohne = await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "vorgang_id": str(va.id)}
    )
    rid = created.json()["id"]
    assert created.json()["positionen"] == []
    headers = auth_headers(token)

    # zeit-Position: SVS-Zeile bleibt unberuehrt
    resp = await client.post(
        f"/api/rechnungen/{rid}/positionen",
        headers=headers,
        json={"beschreibung": "Arbeitszeit", "menge": "2", "einheit": "Std", "einzelpreis": "50", "quelle": "zeit"},
    )
    assert resp.status_code == 200, resp.text
    zeit_pos = resp.json()["positionen"][0]
    e_svs, e_ohne = await _zeilen(svs_zeile, ohne)
    assert e_svs.buchungsstatus == "gebucht"
    assert e_ohne.buchungsstatus == "abgerechnet"

    # leistung-Position: nur die SVS-Zeile wird gesperrt
    resp = await client.post(
        f"/api/rechnungen/{rid}/positionen",
        headers=headers,
        json={
            "beschreibung": "Stundensatz Monteur",
            "menge": "1",
            "einheit": "Std",
            "einzelpreis": "65",
            "quelle": "leistung",
            "lv_position_id": str(svs.id),
        },
    )
    assert resp.status_code == 200, resp.text
    leistung_pos = next(p for p in resp.json()["positionen"] if p["quelle"] == "leistung")
    assert leistung_pos["vorgang_id"] == str(va.id)
    assert leistung_pos["lv_position_id"] == str(svs.id)
    e_svs, e_ohne = await _zeilen(svs_zeile, ohne)
    assert e_svs.buchungsstatus == "abgerechnet"

    # zeit-Position entfernen: SVS-Zeile bleibt gesperrt
    await client.delete(f"/api/rechnungen/{rid}/positionen/{zeit_pos['id']}", headers=headers)
    e_svs, e_ohne = await _zeilen(svs_zeile, ohne)
    assert e_svs.buchungsstatus == "abgerechnet"
    assert e_ohne.buchungsstatus == "gebucht"

    # leistung-Position entfernen: SVS-Zeile frei
    await client.delete(f"/api/rechnungen/{rid}/positionen/{leistung_pos['id']}", headers=headers)
    e_svs, _ = await _zeilen(svs_zeile, ohne)
    assert e_svs.buchungsstatus == "gebucht" and e_svs.abgerechnet_rechnung_id is None


@pytest.mark.asyncio
async def test_freigabe_und_restore_beruehren_keinen_fremden_mandanten(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="MandantA")
    mandant_b = await make_mandant(name="MandantB")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin")
    kunde_a = await make_kunde(mandant=mandant_a)
    vorgang_a = await make_vorgang(mandant=mandant_a, kunde=kunde_a)

    from app.models.rechnung import Rechnung

    async with system_session() as session:
        rechnung = Rechnung(
            mandant_id=mandant_a.id, kunde_id=kunde_a.id, rechnungsnummer="R-RLS-1", betrag_netto=Decimal("0"),
            mwst_satz=Decimal("19"), erstellt_von=admin_a.id,
        )
        session.add(rechnung)
        await session.flush()
        zeile = await _zeit(session, mandant=mandant_a, vorgang=vorgang_a, techniker=admin_a, stunden=1, status="abgerechnet")
        (await session.get(Zeiterfassung, zeile)).abgerechnet_rechnung_id = rechnung.id
        rechnung_id = rechnung.id

    # Als Mandant B: Freigabe, Wieder-Sperren und Verweis-Loesen sehen die Zeile nicht
    async with tenant_session(mandant_id=mandant_b.id, is_super_admin=False) as session:
        await rechnung_service.zeiterfassung_freigeben_fuer_rechnung(
            session, rechnung_id=rechnung_id, geaendert_von=None, verweis_behalten=False
        )
        await rechnung_service.zeiterfassung_wieder_sperren_fuer_rechnung(
            session, rechnung_id=rechnung_id, geaendert_von=None
        )
        await rechnung_service.zeiterfassung_verweis_loesen(session, rechnung_id=rechnung_id)
    (e,) = await _zeilen(zeile)
    assert e.buchungsstatus == "abgerechnet"
    assert e.abgerechnet_rechnung_id == rechnung_id

    # Als Mandant A funktioniert dieselbe Freigabe
    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        await rechnung_service.zeiterfassung_freigeben_fuer_rechnung(
            session, rechnung_id=rechnung_id, geaendert_von=None, verweis_behalten=False
        )
    (e,) = await _zeilen(zeile)
    assert e.buchungsstatus == "gebucht" and e.abgerechnet_rechnung_id is None
