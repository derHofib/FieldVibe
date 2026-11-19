"""MCP-Tools telefonat_erfassen / telefonate_auflisten: Kennzeichnung, Rechte, Mandantentrennung, Allowlist."""
import json
import uuid

from sqlalchemy import func, select

from app.db.session import system_session
from app.mcp.rest_client import schreibaufruf_erlaubt
from app.models.audit_log import AuditLog
from app.models.telefonat import Telefonat
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from tests.mcp_helfer import (
    LESEN,
    SCHREIBEN,
    ki_modul_setzen,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    tool_aufrufen,
    verbinden,
)


async def _admin(make_mandant, make_user):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    return mandant, await make_user(mandant=mandant, role="mandant_admin")


async def test_allowlist_nur_post_auf_telefonate():
    assert schreibaufruf_erlaubt("POST", "/api/telefonate")
    sid = uuid.uuid4()
    assert not schreibaufruf_erlaubt("PATCH", f"/api/telefonate/{sid}")
    assert not schreibaufruf_erlaubt("DELETE", f"/api/telefonate/{sid}")


async def test_telefonat_erfassen_am_vorgang_kennzeichnet_via_claude(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "telefonat_erfassen",
        {
            "vorgang_id": str(vorgang.id), "partner_name": "Frau Brandt", "partner_nummer": "0221 555",
            "richtung": "eingehend", "ergebnis": "erreicht", "dauer_minuten": 7,
            "notiz": "Termin verschoben", "rueckruf_am": "2030-01-01T09:00:00+00:00",
        },
    )
    assert r["fehler"] is False, r
    async with system_session(grund="test") as db:
        tel = (await db.execute(select(Telefonat))).scalar_one()
        events = (await db.execute(select(VorgangEvent).where(VorgangEvent.event_type == "telefonat"))).scalars().all()
        zeiten = (await db.execute(select(func.count()).select_from(Zeiterfassung))).scalar_one()
        audit = (await db.execute(select(AuditLog).where(AuditLog.payload["quelle"].astext == "ki", AuditLog.entity_type == "telefonat"))).scalars().all()
    assert tel.erstellt_via == "claude" and tel.dauer_sekunden == 420 and tel.erfasst_von == admin.id
    assert tel.rueckruf_am is not None and tel.richtung == "eingehend"
    (event,) = events
    assert event.payload["via"] == "claude" and event.payload["ki_verbindung_id"] and event.kundensichtbar is False
    # Arbeitszeit bucht Claude nie.
    assert zeiten == 0
    assert audit, "KI-Schreibzugriff muss im Audit-Log mit quelle=ki stehen"


async def test_telefonat_erfassen_am_kunden_und_fehlerfaelle(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    basis = {"partner_name": "Herr Roth", "richtung": "ausgehend", "ergebnis": "mailbox"}
    ok = await tool_aufrufen(mcp_client, t["access_token"], "telefonat_erfassen", {**basis, "kunde_id": str(kunde.id)})
    assert ok["fehler"] is False, ok
    ohne_bezug = await tool_aufrufen(mcp_client, t["access_token"], "telefonat_erfassen", basis)
    assert ohne_bezug["fehler"] is True and "vorgang_id oder kunde_id" in ohne_bezug["text"]
    ohne_notiz = await tool_aufrufen(
        mcp_client, t["access_token"], "telefonat_erfassen", {**basis, "ergebnis": "erreicht", "kunde_id": str(kunde.id)}
    )
    assert ohne_notiz["fehler"] is True and "Notiz" in ohne_notiz["text"]


async def test_lese_token_kann_telefonat_nicht_erfassen(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    t = await verbinden(mcp_client, admin, [LESEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "telefonat_erfassen",
        {"kunde_id": str(kunde.id), "partner_name": "x", "richtung": "ausgehend", "ergebnis": "mailbox"},
    )
    assert r["fehler"] is True and "fieldvibe.schreiben" in r["text"]
    async with system_session(grund="test") as db:
        assert (await db.execute(select(func.count()).select_from(Telefonat))).scalar_one() == 0


async def test_mandant_b_kann_nicht_an_fremdem_vorgang_erfassen_oder_lesen(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant_a, admin_a = await _admin(make_mandant, make_user)
    mandant_b, admin_b = await _admin(make_mandant, make_user)
    kunde_a = await make_kunde(mandant=mandant_a)
    vorgang_a = await make_vorgang(mandant=mandant_a, kunde=kunde_a)
    ta = await verbinden(mcp_client, admin_a, [LESEN, SCHREIBEN])
    await tool_aufrufen(
        mcp_client, ta["access_token"], "telefonat_erfassen",
        {"vorgang_id": str(vorgang_a.id), "partner_name": "A", "richtung": "ausgehend", "ergebnis": "mailbox"},
    )
    tb = await verbinden(mcp_client, admin_b, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, tb["access_token"], "telefonat_erfassen",
        {"vorgang_id": str(vorgang_a.id), "partner_name": "B", "richtung": "ausgehend", "ergebnis": "mailbox"},
    )
    assert r["fehler"] is True and "Nicht gefunden" in r["text"]
    liste = await tool_aufrufen(mcp_client, tb["access_token"], "telefonate_auflisten", {})
    assert liste["fehler"] is False and json.loads(liste["text"])["eintraege"] == []


async def test_telefonate_auflisten_mit_filtern(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    await tool_aufrufen(
        mcp_client, t["access_token"], "telefonat_erfassen",
        {"vorgang_id": str(vorgang.id), "partner_name": "Mit Rückruf", "richtung": "ausgehend", "ergebnis": "mailbox",
         "rueckruf_am": "2030-01-01T09:00:00+00:00"},
    )
    await tool_aufrufen(
        mcp_client, t["access_token"], "telefonat_erfassen",
        {"kunde_id": str(kunde.id), "partner_name": "Ohne Rückruf", "richtung": "eingehend", "ergebnis": "nicht_erreicht"},
    )

    async def _namen(**args):
        r = await tool_aufrufen(mcp_client, t["access_token"], "telefonate_auflisten", args)
        assert r["fehler"] is False, r
        return {e["partner_name"] for e in json.loads(r["text"])["eintraege"]}

    assert await _namen() == {"Mit Rückruf", "Ohne Rückruf"}
    assert await _namen(rueckruf_offen=True) == {"Mit Rückruf"}
    assert await _namen(vorgang_id=str(vorgang.id)) == {"Mit Rückruf"}
    assert await _namen(kunde_id=str(kunde.id)) == {"Mit Rückruf", "Ohne Rückruf"}
