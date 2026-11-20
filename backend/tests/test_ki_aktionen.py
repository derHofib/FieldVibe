"""KI-Journal: REST-API /api/ki/aktionen (Sichtbarkeit, RLS, Filter) und Rueckgaengig (Frist, Konflikt, Erfolg)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import system_session, tenant_session
from app.models.audit_log import AuditLog
from app.models.auftrag import Auftrag
from app.models.ki_aktion import KiAktion
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login
from tests.mcp_helfer import custom_nutzer, ki_modul_setzen


async def _einrichten(make_mandant, make_user):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    return mandant, admin


async def _nutzer(mandant):
    return await custom_nutzer(mandant, "Büro", {"vorgaenge": ("sehen", "bearbeiten"), "ki_zugriff": ("sehen", "bearbeiten")})


async def _aktion(mandant, user, **kw) -> KiAktion:
    werte = dict(
        mandant_id=mandant.id,
        user_id=user.id,
        tool="verknuepfen",
        aktionsart="vorgang.verknuepfen",
        stufe=2,
        status="ausgefuehrt",
        zusammenfassung="Vorgang mit Auftrag verknüpft",
        ziele=[{"typ": "vorgang", "id": str(uuid.uuid4()), "label": "V-1 Pumpe"}],
        aenderungen=[],
        erzeugt=[],
        rueckweg=[],
    )
    werte.update(kw)
    async with system_session(grund="test") as session:
        a = KiAktion(**werte)
        session.add(a)
        await session.flush()
        await session.refresh(a)
        return a


async def _token(client, user, passwort="pw-123456") -> dict:
    return auth_headers(await login(client, user.email, passwort))


async def test_mandant_b_sieht_nichts_von_a(client, make_mandant, make_user):
    mandant_a, admin_a = await _einrichten(make_mandant, make_user)
    mandant_b, admin_b = await _einrichten(make_mandant, make_user)
    a = await _aktion(mandant_a, admin_a)

    antwort = await client.get("/api/ki/aktionen", headers=await _token(client, admin_b))
    assert antwort.status_code == 200 and antwort.json() == {"eintraege": [], "gesamt": 0}
    assert (await client.get(f"/api/ki/aktionen/{a.id}", headers=await _token(client, admin_b))).status_code == 404
    assert (await client.post(f"/api/ki/aktionen/{a.id}/rueckgaengig", headers=await _token(client, admin_b))).status_code == 404

    # RLS auch direkt in der Datenbank: tenant_session von B sieht die Zeile nicht.
    async with tenant_session(mandant_id=mandant_b.id) as session:
        assert (await session.execute(select(KiAktion))).scalars().all() == []
    async with tenant_session(mandant_id=mandant_a.id) as session:
        assert len((await session.execute(select(KiAktion))).scalars().all()) == 1


async def test_nicht_admin_sieht_nur_eigene_admin_alle(client, make_mandant, make_user):
    mandant, admin = await _einrichten(make_mandant, make_user)
    nutzer = await _nutzer(mandant)
    andere = await _nutzer(mandant)
    eigene = await _aktion(mandant, nutzer, zusammenfassung="Eigene")
    fremde = await _aktion(mandant, andere, zusammenfassung="Fremde")

    h = {"Authorization": f"Bearer {await login(client, nutzer.email, 'hunter2!!')}"}
    liste = (await client.get("/api/ki/aktionen", headers=h)).json()
    assert [e["id"] for e in liste["eintraege"]] == [str(eigene.id)] and liste["gesamt"] == 1
    # user_id-Filter wirkt nur fuer Admins: ein Nutzer bekommt trotzdem nur seine eigenen.
    gefiltert = (await client.get("/api/ki/aktionen", params={"user_id": str(andere.id)}, headers=h)).json()
    assert [e["id"] for e in gefiltert["eintraege"]] == [str(eigene.id)]
    assert (await client.get(f"/api/ki/aktionen/{fremde.id}", headers=h)).status_code == 404

    ha = await _token(client, admin)
    alle = (await client.get("/api/ki/aktionen", headers=ha)).json()
    assert {e["id"] for e in alle["eintraege"]} == {str(eigene.id), str(fremde.id)}
    nur_andere = (await client.get("/api/ki/aktionen", params={"user_id": str(andere.id)}, headers=ha)).json()
    assert [e["id"] for e in nur_andere["eintraege"]] == [str(fremde.id)]
    assert alle["eintraege"][0]["user_name"]


async def test_filter_paging_und_antwortform(client, make_mandant, make_user):
    mandant, admin = await _einrichten(make_mandant, make_user)
    ha = await _token(client, admin)
    await _aktion(
        mandant, admin,
        zusammenfassung="Vorgang V-1 an Auftrag A hängen",
        aenderungen=[{
            "typ": "vorgang", "id": "x", "label": "V-1", "feld": "auftrag_id", "feld_label": "Auftrag",
            "vorher": {"wert": None, "anzeige": None}, "nachher": {"wert": "abc", "anzeige": "Sanierung Lindenstraße"},
        }],
        rueckweg=[{"methode": "PATCH", "pfad": "/api/vorgaenge/x", "body": {"auftrag_id": None}, "pruefung": None}],
        rueckgaengig_bis=datetime.now(timezone.utc) + timedelta(days=7),
    )
    await _aktion(mandant, admin, zusammenfassung="Termin verschoben", status="rueckgaengig")
    await _aktion(mandant, admin, zusammenfassung="Alt", erstellt_am=datetime.now(timezone.utc) - timedelta(days=10))

    assert (await client.get("/api/ki/aktionen", params={"status": "rueckgaengig"}, headers=ha)).json()["gesamt"] == 1
    assert (await client.get("/api/ki/aktionen", params={"q": "lindenstr"}, headers=ha)).json()["gesamt"] == 0  # nur Zusammenfassung
    assert (await client.get("/api/ki/aktionen", params={"q": "AUFTRAG"}, headers=ha)).json()["gesamt"] == 1
    heute = datetime.now(timezone.utc).date().isoformat()
    assert (await client.get("/api/ki/aktionen", params={"von": heute}, headers=ha)).json()["gesamt"] == 2
    assert (await client.get("/api/ki/aktionen", params={"bis": (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()}, headers=ha)).json()["gesamt"] == 1
    seite = (await client.get("/api/ki/aktionen", params={"limit": 1, "offset": 1}, headers=ha)).json()
    assert seite["gesamt"] == 3 and len(seite["eintraege"]) == 1
    assert (await client.get("/api/ki/aktionen", params={"limit": 500}, headers=ha)).status_code == 422
    assert (await client.get("/api/ki/aktionen", params={"status": "kaputt"}, headers=ha)).status_code == 422

    mit_aenderung = next(e for e in (await client.get("/api/ki/aktionen", headers=ha)).json()["eintraege"] if e["aenderungen"])
    assert mit_aenderung["aenderungen"][0] == {
        "typ": "vorgang", "id": "x", "label": "V-1", "feld": "auftrag_id", "feld_label": "Auftrag",
        "vorher": None, "nachher": "Sanierung Lindenstraße",
    }
    assert mit_aenderung["rueckgaengig_moeglich"] is True and mit_aenderung["rueckgaengig_bis"]
    # Nie ausliefern: Rueckweg, Eingabe, rohe Werte.
    assert not {"rueckweg", "eingabe", "vorschau"} & mit_aenderung.keys()


async def test_zugang_modul_recht_und_kein_mcp_token(client, make_mandant, make_user):
    mandant, admin = await _einrichten(make_mandant, make_user)
    ohne_recht = await custom_nutzer(mandant, "Ohne", {"vorgaenge": ("sehen",)})
    h = {"Authorization": f"Bearer {await login(client, ohne_recht.email, 'hunter2!!')}"}
    assert (await client.get("/api/ki/aktionen", headers=h)).status_code == 403

    mcp = create_access_token(
        subject=admin.id, role=admin.role, mandant_id=mandant.id, token_version=admin.token_version,
        via="mcp", ki_verbindung_id=uuid.uuid4(), expires_delta=timedelta(minutes=2),
    )
    assert (await client.get("/api/ki/aktionen", headers=auth_headers(mcp))).status_code == 403

    await ki_modul_setzen(mandant, aktiv=False)
    assert (await client.get("/api/ki/aktionen", headers=await _token(client, admin))).status_code == 403


# --- Rueckgaengig ---------------------------------------------------------------------------------


async def _vorgang_mit_auftrag(mandant, admin, make_kunde, make_vorgang):
    kunde = await make_kunde(mandant=mandant)
    async with system_session(grund="test") as session:
        alt = Auftrag(mandant_id=mandant.id, titel="Wartung 2026", erstellt_von=admin.id)
        neu = Auftrag(mandant_id=mandant.id, titel="Sanierung Lindenstraße", erstellt_von=admin.id)
        session.add_all([alt, neu])
        await session.flush()
        alt_id, neu_id = alt.id, neu.id
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=neu_id)
    return vorgang, alt_id, neu_id


def _verknuepfung_aktion(vorgang, alt_id, neu_id) -> dict:
    pfad = f"/api/vorgaenge/{vorgang.id}"
    return dict(
        ziele=[{"typ": "vorgang", "id": str(vorgang.id), "label": "V Test"}],
        aenderungen=[{
            "typ": "vorgang", "id": str(vorgang.id), "label": "V Test", "feld": "auftrag_id", "feld_label": "Auftrag",
            "vorher": {"wert": str(alt_id), "anzeige": "Wartung 2026"},
            "nachher": {"wert": str(neu_id), "anzeige": "Sanierung Lindenstraße"},
        }],
        rueckweg=[{
            "methode": "PATCH", "pfad": pfad, "body": {"auftrag_id": str(alt_id)},
            "pruefung": [{
                "pfad": pfad, "feld": "auftrag_id", "erwartet": str(neu_id), "label": "V Test",
                "feld_label": "Auftrag", "erwartet_anzeige": "Sanierung Lindenstraße", "anzeige_feld": "auftrag_titel",
            }],
        }],
        rueckgaengig_bis=datetime.now(timezone.utc) + timedelta(days=7),
    )


async def _vorgang(vorgang_id) -> Vorgang:
    async with system_session(grund="test") as session:
        return await session.get(Vorgang, vorgang_id)


async def test_rueckgaengig_erfolg_setzt_werte_zurueck(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin = await _einrichten(make_mandant, make_user)
    vorgang, alt_id, neu_id = await _vorgang_mit_auftrag(mandant, admin, make_kunde, make_vorgang)
    aktion = await _aktion(mandant, admin, **_verknuepfung_aktion(vorgang, alt_id, neu_id))
    h = await _token(client, admin)

    antwort = await client.post(f"/api/ki/aktionen/{aktion.id}/rueckgaengig", headers=h)
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    assert body["status"] == "rueckgaengig" and body["rueckgaengig_moeglich"] is False
    assert body["rueckgaengig_am"] and body["rueckgaengig_von_name"] == admin.name
    assert (await _vorgang(vorgang.id)).auftrag_id == alt_id

    # Zweites Mal geht nicht, und es steht ein Audit-Eintrag.
    assert (await client.post(f"/api/ki/aktionen/{aktion.id}/rueckgaengig", headers=h)).status_code == 400
    async with system_session(grund="test") as session:
        eintraege = (await session.execute(select(AuditLog).where(AuditLog.aktion == "ki_aktion_rueckgaengig"))).scalars().all()
    assert len(eintraege) == 1 and eintraege[0].entity_id == aktion.id and eintraege[0].payload["ausloeser"] == "app"


async def test_rueckgaengig_konflikt_aendert_nichts(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin = await _einrichten(make_mandant, make_user)
    vorgang, alt_id, neu_id = await _vorgang_mit_auftrag(mandant, admin, make_kunde, make_vorgang)
    aktion = await _aktion(mandant, admin, **_verknuepfung_aktion(vorgang, alt_id, neu_id))
    h = await _token(client, admin)

    # Jemand ordnet den Vorgang manuell wieder dem alten Auftrag zu -> Wert ist nicht mehr "nachher".
    async with system_session(grund="test") as session:
        v = await session.get(Vorgang, vorgang.id)
        v.auftrag_id = None
    antwort = await client.post(f"/api/ki/aktionen/{aktion.id}/rueckgaengig", headers=h)
    assert antwort.status_code == 409, antwort.text
    detail = antwort.json()["detail"]
    assert detail["konflikte"] == [
        {"label": "V Test", "feld_label": "Auftrag", "erwartet_anzeige": "Sanierung Lindenstraße", "aktuell_anzeige": None}
    ]
    assert "geändert" in detail["meldung"]
    assert (await _vorgang(vorgang.id)).auftrag_id is None
    assert (await client.get(f"/api/ki/aktionen/{aktion.id}", headers=h)).json()["status"] == "ausgefuehrt"


async def test_rueckgaengig_frist_status_und_ohne_rueckweg(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin = await _einrichten(make_mandant, make_user)
    vorgang, alt_id, neu_id = await _vorgang_mit_auftrag(mandant, admin, make_kunde, make_vorgang)
    h = await _token(client, admin)

    abgelaufen = await _aktion(mandant, admin, **{**_verknuepfung_aktion(vorgang, alt_id, neu_id), "rueckgaengig_bis": datetime.now(timezone.utc) - timedelta(minutes=1)})
    r = await client.post(f"/api/ki/aktionen/{abgelaufen.id}/rueckgaengig", headers=h)
    assert r.status_code == 400 and "Frist" in r.json()["detail"]
    assert (await client.get(f"/api/ki/aktionen/{abgelaufen.id}", headers=h)).json()["rueckgaengig_moeglich"] is False

    ohne = await _aktion(mandant, admin)  # rueckweg leer
    r = await client.post(f"/api/ki/aktionen/{ohne.id}/rueckgaengig", headers=h)
    assert r.status_code == 400 and "nicht rückgängig" in r.json()["detail"]
    assert (await _vorgang(vorgang.id)).auftrag_id == neu_id


async def test_rueckgaengig_durch_fremden_nicht_admin_ist_403(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin = await _einrichten(make_mandant, make_user)
    vorgang, alt_id, neu_id = await _vorgang_mit_auftrag(mandant, admin, make_kunde, make_vorgang)
    fremder = await _nutzer(mandant)
    aktion = await _aktion(mandant, admin, **_verknuepfung_aktion(vorgang, alt_id, neu_id))

    h = {"Authorization": f"Bearer {await login(client, fremder.email, 'hunter2!!')}"}
    assert (await client.post(f"/api/ki/aktionen/{aktion.id}/rueckgaengig", headers=h)).status_code == 403
    assert (await _vorgang(vorgang.id)).auftrag_id == neu_id

    # Eigentuemer ohne Admin-Rolle darf.
    eigene = await _aktion(mandant, fremder, **_verknuepfung_aktion(vorgang, alt_id, neu_id))
    assert (await client.post(f"/api/ki/aktionen/{eigene.id}/rueckgaengig", headers=h)).status_code == 200
    assert (await _vorgang(vorgang.id)).auftrag_id == alt_id
