"""MCP-Schreib-Tools (Etappe 2): Scope und Recht, KI-Kennzeichnung, Mandantentrennung, Allowlist."""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.db.session import system_session
from app.mcp import rest_client
from app.mcp.server import SCHREIB_TOOLS
from app.models.account_typ import AccountTypRecht
from app.models.audit_log import AuditLog
from app.models.mangel import Mangel
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login
from tests.mcp_helfer import (
    LESEN,
    PASSWORT,
    SCHREIBEN,
    custom_nutzer,
    ki_modul_setzen,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    mcp_rpc,
    tool_aufrufen,
    verbinden,
)

ALLE_SCHREIB_TOOLS = {
    "kommentar_anlegen",
    "mangel_erfassen",
    "vorgang_anlegen",
    "protokoll_entwurf_anlegen",
    "protokoll_entwurf_ergaenzen",
    "protokoll_vorlage_entwerfen",
    "protokoll_vorlage_ueberarbeiten",
}


async def _admin(make_mandant, make_user, scopes=None):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    return mandant, admin


async def _tools(mcp_client, token):
    return (await mcp_rpc(mcp_client, token, "tools/list")).json()["result"]["tools"]


async def _events(vorgang_id, event_type=None) -> list[VorgangEvent]:
    async with system_session(grund="test") as session:
        stmt = select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang_id).order_by(VorgangEvent.id)
        if event_type:
            stmt = stmt.where(VorgangEvent.event_type == event_type)
        return list((await session.execute(stmt)).scalars().all())


# --- Scope und Recht -----------------------------------------------------------------------


def test_schreib_tools_der_server_liste_sind_vollstaendig():
    assert SCHREIB_TOOLS == ALLE_SCHREIB_TOOLS


async def test_lese_token_sieht_keine_schreib_tools_und_kann_sie_nicht_aufrufen(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    t = await verbinden(mcp_client, admin, [LESEN])
    namen = {x["name"] for x in await _tools(mcp_client, t["access_token"])}
    assert not namen & ALLE_SCHREIB_TOOLS
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang.id), "text": "Hallo"}
    )
    assert r["fehler"] is True and "fieldvibe.schreiben" in r["text"]
    assert await _events(vorgang.id, "kommentar") == []


async def test_schreib_token_listet_alle_schreib_tools_mit_additiven_annotations(make_mandant, make_user, mcp_client):
    _, admin = await _admin(make_mandant, make_user)
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    tools = {x["name"]: x for x in await _tools(mcp_client, t["access_token"])}
    assert ALLE_SCHREIB_TOOLS <= set(tools)
    for name in ALLE_SCHREIB_TOOLS:
        a = tools[name]["annotations"]
        assert a["readOnlyHint"] is False and a["destructiveHint"] is False and a["idempotentHint"] is False, name
        assert "nur mit Schreibzugriff" in tools[name]["description"], name
    # Nichts, was loescht, abschliesst, veroeffentlicht oder versendet.
    for name in tools:
        assert not any(w in name for w in ("loeschen", "abschliessen", "veroeffentlichen", "senden", "freigeben", "export")), name


async def test_entzogenes_schreibrecht_wirkt_beim_naechsten_aufruf(make_mandant, make_kunde, make_vorgang, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    kunde = await make_kunde(mandant=mandant)
    nutzer = await custom_nutzer(
        mandant, "Büro", {"vorgaenge": ("sehen", "erstellen"), "ki_zugriff": ("sehen", "bearbeiten")}
    )
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    t = await verbinden(mcp_client, nutzer, [LESEN, SCHREIBEN])
    assert SCHREIBEN in t["scope"]
    ok = await tool_aufrufen(mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang.id), "text": "Eins"})
    assert ok["fehler"] is False, ok

    async with system_session(grund="test") as session:
        await session.execute(
            delete(AccountTypRecht).where(
                AccountTypRecht.account_typ_id == nutzer.account_typ_id,
                AccountTypRecht.bereich == "ki_zugriff",
                AccountTypRecht.aktion == "bearbeiten",
            )
        )
    abgelehnt = await tool_aufrufen(
        mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang.id), "text": "Zwei"}
    )
    assert abgelehnt["fehler"] is True and "ki_zugriff" not in abgelehnt["text"] and "bearbeiten" in abgelehnt["text"]
    assert not {x["name"] for x in await _tools(mcp_client, t["access_token"])} & ALLE_SCHREIB_TOOLS
    assert [e.body for e in await _events(vorgang.id, "kommentar")] == ["Eins"]
    # Lesen geht weiter.
    assert (await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(vorgang.id)}))["fehler"] is False


# --- Kommentar, Mangel, Vorgang -------------------------------------------------------------


async def test_kommentar_traegt_ki_kennzeichnung_und_audit_quelle_ki(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang.id), "text": "Besprechung mit Kunde"}
    )
    assert r["fehler"] is False, r
    [event] = await _events(vorgang.id, "kommentar")
    assert event.body == "Besprechung mit Kunde" and event.kundensichtbar is False
    assert event.payload["via"] == "claude" and event.payload["ki_verbindung_id"]
    assert event.author_user_id == admin.id
    async with system_session(grund="test") as session:
        eintraege = (
            await session.execute(select(AuditLog).where(AuditLog.mandant_id == mandant.id, AuditLog.payload["quelle"].astext == "ki"))
        ).scalars().all()
    assert eintraege, "Schreibaufruf per KI muss mindestens einen Audit-Eintrag mit quelle=ki haben"


async def test_kennzeichnung_ist_nicht_per_client_payload_faelschbar(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    kopf = auth_headers(await login(mcp_client, admin.email, PASSWORT))
    r = await mcp_client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        json={"event_type": "kommentar", "body": "Mensch", "payload": {"via": "claude", "x": 1}},
        headers=kopf,
    )
    assert r.status_code == 201
    [event] = await _events(vorgang.id, "kommentar")
    assert event.payload == {"x": 1}


async def test_kommentar_an_abgeschlossenem_vorgang_wird_abgelehnt(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant), status="abgeschlossen")
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang.id), "text": "x"})
    assert r["fehler"] is True and "abgeschlossen" in r["text"]


async def test_mandant_b_kann_nicht_an_vorgang_von_a_schreiben(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant_a, _ = await _admin(make_mandant, make_user)
    mandant_b, admin_b = await _admin(make_mandant, make_user)
    kunde_a = await make_kunde(mandant=mandant_a)
    vorgang_a = await make_vorgang(mandant=mandant_a, kunde=kunde_a)
    tb = await verbinden(mcp_client, admin_b, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(mcp_client, tb["access_token"], "kommentar_anlegen", {"vorgang_id": str(vorgang_a.id), "text": "Eindringling"})
    assert r["fehler"] is True and "Nicht gefunden" in r["text"]
    m = await tool_aufrufen(
        mcp_client, tb["access_token"], "mangel_erfassen", {"vorgang_id": str(vorgang_a.id), "beschreibung": "x"}
    )
    assert m["fehler"] is True
    v = await tool_aufrufen(
        mcp_client, tb["access_token"], "vorgang_anlegen",
        {"kunde_id": str(kunde_a.id), "titel": "Fremd", "leistungstyp": "wartung"},
    )
    assert v["fehler"] is True
    assert await _events(vorgang_a.id, "kommentar") == []
    async with system_session(grund="test") as session:
        assert (await session.execute(select(Mangel).where(Mangel.vorgang_id == vorgang_a.id))).first() is None
        assert (await session.execute(select(Vorgang).where(Vorgang.titel == "Fremd"))).first() is None


async def test_techniker_mit_scope_eigene_kann_nicht_an_fremdem_vorgang_kommentieren(
    make_mandant, make_kunde, make_vorgang, mcp_client
):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    kunde = await make_kunde(mandant=mandant)
    tech = await custom_nutzer(
        mandant,
        "Techniker",
        {"vorgaenge": ("sehen", "bearbeiten", "erstellen"), "ki_zugriff": ("sehen", "bearbeiten")},
        scopes_je_bereich={"vorgaenge": "eigene", "ki_zugriff": "mandant"},
    )
    kollege = await custom_nutzer(mandant, "Kollege", {"vorgaenge": ("sehen",)})
    eigener = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech.id)
    fremder = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=kollege.id)
    t = await verbinden(mcp_client, tech, [LESEN, SCHREIBEN])
    ok = await tool_aufrufen(mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(eigener.id), "text": "Mein"})
    assert ok["fehler"] is False, ok
    nein = await tool_aufrufen(mcp_client, t["access_token"], "kommentar_anlegen", {"vorgang_id": str(fremder.id), "text": "Fremd"})
    assert nein["fehler"] is True
    assert await _events(fremder.id, "kommentar") == []


async def test_mangel_erfassen_status_offen_mit_kennzeichnung(make_mandant, make_user, make_kunde, make_vorgang, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "mangel_erfassen",
        {"vorgang_id": str(vorgang.id), "beschreibung": "Abgasrohr undicht", "schweregrad": "hoch"},
    )
    assert r["fehler"] is False, r
    assert r["daten"]["status"] == "offen" and r["daten"]["schweregrad"] == "hoch"
    [event] = await _events(vorgang.id, "mangel")
    assert event.payload["via"] == "claude" and event.payload["mangel_id"] == r["daten"]["id"]
    falsch = await tool_aufrufen(
        mcp_client, t["access_token"], "mangel_erfassen",
        {"vorgang_id": str(vorgang.id), "beschreibung": "x", "schweregrad": "katastrophal"},
    )
    assert falsch["fehler"] is True


async def test_vorgang_anlegen_status_neu_ohne_zuweisung_und_kennzeichnung(make_mandant, make_user, make_kunde, mcp_client):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    t = await verbinden(mcp_client, admin, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "vorgang_anlegen",
        {"kunde_id": str(kunde.id), "titel": "Therme macht Geräusche", "beschreibung": "Seit gestern", "leistungstyp": "stoerung"},
    )
    assert r["fehler"] is False, r
    assert r["daten"]["status"] == "neu" and r["daten"]["abrechnungsart"] == "aufwand"
    async with system_session(grund="test") as session:
        v = await session.get(Vorgang, uuid.UUID(r["daten"]["id"]))
    assert v.zugewiesener_user_id is None and v.erstellt_von == admin.id and v.status == "neu"
    [angelegt] = await _events(v.id, "system")
    assert angelegt.payload["via"] == "claude"
    ohne_typ = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_anlegen", {"kunde_id": str(kunde.id), "titel": "x"})
    assert ohne_typ["fehler"] is True


async def test_ohne_fachrecht_kommt_verstaendlicher_fehler(make_mandant, make_kunde, make_vorgang, mcp_client):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    kunde = await make_kunde(mandant=mandant)
    nutzer = await custom_nutzer(mandant, "Nur KI", {"vorgaenge": ("sehen",), "ki_zugriff": ("sehen", "bearbeiten")})
    t = await verbinden(mcp_client, nutzer, [LESEN, SCHREIBEN])
    r = await tool_aufrufen(
        mcp_client, t["access_token"], "vorgang_anlegen", {"kunde_id": str(kunde.id), "titel": "x", "leistungstyp": "wartung"}
    )
    assert r["fehler"] is True and "Dafür fehlt dir das Recht" in r["text"]


# --- Allowlist ----------------------------------------------------------------------------------

_ID = "11111111-2222-3333-4444-555555555555"


@pytest.mark.parametrize(
    "methode,pfad",
    [
        ("POST", "/api/vorgaenge"),
        ("POST", f"/api/vorgaenge/{_ID}/events"),
        ("POST", "/api/maengel"),
        ("POST", "/api/form-submissions"),
        ("PATCH", f"/api/form-submissions/{_ID}"),
        ("POST", "/api/form-schemas"),
        ("POST", f"/api/form-schemas/{_ID}/groups"),
        ("POST", f"/api/form-schemas/{_ID}/fields"),
        ("PATCH", f"/api/form-schemas/{_ID}/fields/{_ID}"),
    ],
)
def test_allowlist_erlaubt_nur_die_vorgesehenen_schreibwege(methode, pfad):
    assert rest_client.schreibaufruf_erlaubt(methode, pfad)


@pytest.mark.parametrize(
    "methode,pfad",
    [
        ("DELETE", f"/api/vorgaenge/{_ID}"),
        ("DELETE", f"/api/form-schemas/{_ID}"),
        ("DELETE", f"/api/form-schemas/{_ID}/fields/{_ID}"),
        ("DELETE", f"/api/form-submissions/{_ID}"),
        ("DELETE", f"/api/maengel/{_ID}"),
        ("PATCH", f"/api/vorgaenge/{_ID}"),
        ("PATCH", f"/api/form-schemas/{_ID}"),  # Status draft -> published
        ("PATCH", f"/api/form-schemas/{_ID}/groups/{_ID}"),
        ("PATCH", f"/api/maengel/{_ID}"),
        ("POST", f"/api/form-submissions/{_ID}/abschliessen"),
        ("POST", f"/api/form-submissions/{_ID}/dateien"),
        ("POST", f"/api/vorgaenge/{_ID}/abschliessen"),
        ("POST", f"/api/vorgaenge/{_ID}/events/foto"),
        ("POST", f"/api/form-schemas/{_ID}/zuordnungen"),
        ("PATCH", f"/api/form-schemas/{_ID}/views/{_ID}"),
        ("DELETE", f"/api/form-schemas/{_ID}/views/{_ID}"),
        ("PUT", f"/api/form-schemas/{_ID}/views/{_ID}/layouts"),
        ("POST", f"/api/form-schemas/{_ID}/views/{_ID}/elements"),
        ("POST", f"/api/form-schemas/{_ID}/rules"),
        ("PUT", f"/api/form-schemas/{_ID}/groups"),
        ("POST", "/api/angebote"),
        ("POST", "/api/rechnungen"),
        ("POST", "/api/users"),
        ("POST", "/api/vorgaenge/"),
        ("POST", "/api/vorgaenge/../users"),
        ("POST", "/api/vorgaenge/x/events"),
    ],
)
def test_allowlist_blockiert_loeschen_abschliessen_veroeffentlichen_und_rest(methode, pfad):
    assert not rest_client.schreibaufruf_erlaubt(methode, pfad)


async def test_nicht_erlaubter_schreibaufruf_wird_vor_dem_senden_abgebrochen():
    class _Token:  # kein Token noetig: die Pruefung kommt vor der Token-Ausstellung
        pass

    with pytest.raises(PermissionError):
        await rest_client._anfrage(_Token(), "DELETE", f"/api/vorgaenge/{_ID}")
    with pytest.raises(PermissionError):
        await rest_client._anfrage(_Token(), "PATCH", f"/api/form-schemas/{_ID}", body={"status": "published"})


def test_tools_gehen_nur_ueber_den_rest_client():
    """Schreibaufrufe laufen ausschliesslich ueber api_post/api_patch und damit durch die Allowlist."""
    wurzel = Path(__file__).resolve().parents[1] / "app" / "mcp" / "tools"
    for datei in wurzel.glob("*.py"):
        text = datei.read_text(encoding="utf-8")
        assert "httpx" not in text and "api_delete" not in text, datei.name
    assert not hasattr(rest_client, "api_delete") and not hasattr(rest_client, "api_put")
