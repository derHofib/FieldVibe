"""Mandanten-Audit-Log: append-only, Hash-Kette, Einsicht, Ereignisse."""
import asyncio
import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.db.session import engine, system_session, tenant_session
from app.models.audit_log import AuditLog, AuditLogSiegel
from app.models.user import User
from app.services import audit_service
from tests.conftest import auth_headers, login


async def _eintraege(mandant_id, aktion: str | None = None) -> list[AuditLog]:
    async with system_session() as session:
        stmt = select(AuditLog).where(AuditLog.mandant_id == mandant_id).order_by(AuditLog.id)
        if aktion:
            stmt = stmt.where(AuditLog.aktion == aktion)
        return list((await session.execute(stmt)).scalars().all())


async def _admin(client, make_mandant, make_user, name="Betrieb"):
    mandant = await make_mandant(name)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    return mandant, admin, token


def _super(conn):
    # Rohe Verbindung ohne App-Sitzung: die FORCE-RLS braucht den Super-Admin-Kontext.
    return conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))


async def _trigger_aus(tabelle: str):
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {tabelle} DISABLE TRIGGER trg_{tabelle}_append_only"))


async def _trigger_an(tabelle: str):
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {tabelle} ENABLE TRIGGER trg_{tabelle}_append_only"))


@pytest.mark.asyncio
async def test_append_only_auch_fuer_super_admin_kontext(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        eintrag = await audit_service.log_action(session, aktion="test", mandant_id=mandant.id)
        eintrag_id = eintrag.id

    with pytest.raises(DBAPIError, match="append-only"):
        async with system_session() as session:
            await session.execute(update(AuditLog).where(AuditLog.id == eintrag_id).values(aktion="manipuliert"))
    with pytest.raises(DBAPIError, match="append-only"):
        async with system_session() as session:
            await session.execute(text("DELETE FROM audit_log WHERE id = :i"), {"i": eintrag_id})
    with pytest.raises(DBAPIError, match="append-only"):
        async with system_session() as session:
            await session.execute(text("UPDATE audit_log_siegel SET hash = repeat('a', 64)"))


@pytest.mark.asyncio
async def test_kette_wird_gebildet_und_ist_gueltig(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    for i in range(3):
        async with system_session() as session:
            await audit_service.log_action(
                session, aktion=f"test_{i}", mandant_id=mandant.id, actor_user_id=admin.id, payload={"i": i}
            )

    resp = await client.get("/api/audit/verifizieren", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["geprueft"] >= 4  # login + 3 Testeintraege
    assert body["ohne_siegel"] == 0
    assert body["kopf_seq"] == body["geprueft"]

    async with system_session() as session:
        siegel = (
            await session.execute(
                select(AuditLogSiegel).where(AuditLogSiegel.mandant_id == mandant.id).order_by(AuditLogSiegel.seq)
            )
        ).scalars().all()
    assert [s.seq for s in siegel] == list(range(1, len(siegel) + 1))
    assert siegel[0].vorgaenger_hash == audit_service.SIEGEL_GENESIS
    for vorher, nachher in zip(siegel, siegel[1:]):
        assert nachher.vorgaenger_hash == vorher.hash


@pytest.mark.asyncio
async def test_mehrere_eintraege_in_einer_transaktion_werden_in_reihenfolge_verkettet(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        for i in range(5):
            await audit_service.log_action(session, aktion="serie", mandant_id=mandant.id, payload={"i": i})
    async with system_session() as session:
        ergebnis = await audit_service.kette_pruefen(session, mandant.id)
    assert ergebnis.ok and ergebnis.geprueft == 5


@pytest.mark.asyncio
async def test_manipulation_am_inhalt_wird_erkannt(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    async with system_session() as session:
        await audit_service.log_action(
            session, aktion="zahlung_gebucht", mandant_id=mandant.id, actor_user_id=admin.id, payload={"betrag": "100.00"}
        )
    ziel = (await _eintraege(mandant.id, "zahlung_gebucht"))[0]

    await _trigger_aus("audit_log")
    try:
        async with engine.begin() as conn:
            await _super(conn)
            await conn.execute(
                text("UPDATE audit_log SET payload = '{\"betrag\": \"1.00\"}'::jsonb WHERE id = :i"), {"i": ziel.id}
            )
    finally:
        await _trigger_an("audit_log")

    resp = await client.get("/api/audit/verifizieren", headers=auth_headers(token))
    body = resp.json()
    assert body["ok"] is False
    assert any("stimmt nicht" in f["grund"] and f["audit_log_id"] == ziel.id for f in body["fehler"])


@pytest.mark.asyncio
async def test_entferntes_oder_eingeschobenes_siegel_wird_erkannt(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    for i in range(3):
        async with system_session() as session:
            await audit_service.log_action(session, aktion=f"k_{i}", mandant_id=mandant.id, actor_user_id=admin.id)

    # Mittleres Siegel entfernen: Luecke in der Kette.
    await _trigger_aus("audit_log_siegel")
    try:
        async with engine.begin() as conn:
            await _super(conn)
            await conn.execute(
                text("DELETE FROM audit_log_siegel WHERE mandant_id = :m AND seq = 2"), {"m": mandant.id}
            )
    finally:
        await _trigger_an("audit_log_siegel")
    body = (await client.get("/api/audit/verifizieren", headers=auth_headers(token))).json()
    assert body["ok"] is False
    assert any("Lücke" in f["grund"] for f in body["fehler"])

    # Nachtraeglich eingefuegter, nicht gesiegelter Eintrag.
    mandant2, admin2, token2 = await _admin(client, make_mandant, make_user, "Zweitbetrieb")
    async with system_session() as session:
        await audit_service.log_action(session, aktion="echt", mandant_id=mandant2.id)
    async with engine.begin() as conn:
        await _super(conn)
        await conn.execute(
            text(
                "INSERT INTO audit_log (mandant_id, aktion, akteur_typ, payload) "
                "VALUES (:m, 'eingeschmuggelt', 'system', '{}'::jsonb)"
            ),
            {"m": mandant2.id},
        )
    body2 = (await client.get("/api/audit/verifizieren", headers=auth_headers(token2))).json()
    assert body2["ok"] is False
    assert body2["ohne_siegel"] == 1


@pytest.mark.asyncio
async def test_ketten_sind_je_mandant_getrennt(client, make_mandant, make_user):
    m1, a1, t1 = await _admin(client, make_mandant, make_user, "Eins")
    m2, a2, t2 = await _admin(client, make_mandant, make_user, "Zwei")
    async with system_session() as session:
        await audit_service.log_action(session, aktion="nur_eins", mandant_id=m1.id)
    async with system_session() as session:
        siegel = (await session.execute(select(AuditLogSiegel).order_by(AuditLogSiegel.id))).scalars().all()
    assert {s.mandant_id for s in siegel} == {m1.id, m2.id}
    for mid in (m1.id, m2.id):
        assert [s.seq for s in siegel if s.mandant_id == mid][0] == 1

    liste = (await client.get("/api/audit", headers=auth_headers(t2))).json()
    assert all(e["aktion"] != "nur_eins" for e in liste["eintraege"])
    # Unter der RLS-Mandantensession von Mandant 2 ist die Kette von Mandant 1 nicht lesbar.
    async with tenant_session(mandant_id=m2.id, is_super_admin=False) as session:
        assert (await session.execute(select(AuditLogSiegel).where(AuditLogSiegel.mandant_id == m1.id))).first() is None
        assert (await session.execute(select(AuditLog).where(AuditLog.mandant_id == m1.id))).first() is None


@pytest.mark.asyncio
async def test_parallele_schreiber_verklemmen_nicht_und_kette_bleibt_gueltig(make_mandant):
    mandant = await make_mandant()

    async def schreiber(n: int) -> None:
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            # Fachzeile sperren, DANN protokollieren: genau das Muster, das beim Sperren
            # im INSERT-Pfad zu Deadlocks fuehren wuerde.
            await session.execute(select(User).where(User.mandant_id == mandant.id).with_for_update())
            await audit_service.log_action(session, aktion="parallel", mandant_id=mandant.id, payload={"n": n})
            await audit_service.log_action(session, aktion="parallel", mandant_id=mandant.id, payload={"n": n, "b": 1})

    await asyncio.wait_for(asyncio.gather(*(schreiber(n) for n in range(12))), timeout=60)

    async with system_session() as session:
        ergebnis = await audit_service.kette_pruefen(session, mandant.id)
    assert ergebnis.ok, ergebnis.fehler
    assert ergebnis.geprueft == 24


@pytest.mark.asyncio
async def test_audit_fehler_laesst_fachaenderung_scheitern(make_mandant, make_user, monkeypatch):
    """GoBD: kein Beleg ohne Protokoll. Schlaegt das Siegeln fehl, wird auch die
    Fachaenderung derselben Transaktion nicht festgeschrieben."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")

    def kaputt(session):
        raise RuntimeError("Siegel nicht moeglich")

    monkeypatch.setattr(audit_service, "_siegeln", kaputt)
    with pytest.raises(RuntimeError, match="Siegel nicht moeglich"):
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            benutzer = await session.get(User, admin.id)
            benutzer.name = "Geaendert ohne Protokoll"
            await audit_service.log_action(session, aktion="user_geaendert", mandant_id=mandant.id)
    monkeypatch.undo()

    async with system_session() as session:
        assert (await session.get(User, admin.id)).name != "Geaendert ohne Protokoll"
    assert await _eintraege(mandant.id, "user_geaendert") == []


@pytest.mark.asyncio
async def test_siegel_fehler_liefert_http_500_statt_scheinerfolg(client, make_mandant, make_user, make_kunde, monkeypatch):
    """Der COMMIT liefe sonst erst nach dem Senden der Antwort: der Client bekaeme 201,
    obwohl nichts gespeichert ist."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.models.rechnung import Rechnung

    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)

    def kaputt(session):
        if session.info.get("audit_siegel_vorgemerkt"):
            raise RuntimeError("Siegel nicht moeglich")

    monkeypatch.setattr(audit_service, "_siegeln", kaputt)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "100"}
        )
    monkeypatch.undo()
    assert resp.status_code == 500
    async with system_session() as session:
        assert (await session.execute(select(Rechnung))).first() is None
    assert await _eintraege(mandant.id, "rechnung_erstellt") == []


@pytest.mark.asyncio
async def test_zurueckgerollter_savepoint_hinterlaesst_kein_siegel(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        await audit_service.log_action(session, aktion="bleibt", mandant_id=mandant.id)
        try:
            async with session.begin_nested():
                await audit_service.log_action(session, aktion="weg", mandant_id=mandant.id)
                raise ValueError("abbruch")
        except ValueError:
            pass
    assert [e.aktion for e in await _eintraege(mandant.id)] == ["bleibt"]
    async with system_session() as session:
        assert (await audit_service.kette_pruefen(session, mandant.id)).ok


def test_payload_wird_von_geheimnissen_bereinigt_und_ip_gekuerzt():
    assert audit_service.bereinigen({"password": "x", "a": {"api_token": "y", "ok": 1}, "l": [{"secret": 1}]}) == {
        "password": "***",
        "a": {"api_token": "***", "ok": 1},
        "l": [{"secret": "***"}],
    }
    assert audit_service.ip_kuerzen("203.0.113.77") == "203.0.113.0"
    assert audit_service.ip_kuerzen("2001:db8:1234:5678::1") == "2001:db8:1234::/48"
    assert audit_service.ip_kuerzen("kein-ip") is None
    assert audit_service.ip_kuerzen(None) is None


@pytest.mark.asyncio
async def test_login_ereignisse(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")

    falsch = await client.post("/api/auth/login", json={"email": user.email, "password": "falsch-123456"})
    assert falsch.status_code == 401
    unbekannt = await client.post("/api/auth/login", json={"email": "niemand@example.de", "password": "x-123456"})
    assert unbekannt.status_code == 401
    ok = await client.post("/api/auth/login", json={"email": user.email, "password": "pw-123456"})
    assert ok.status_code == 200

    fehl = await _eintraege(mandant.id, "login_fehlgeschlagen")
    assert len(fehl) == 1
    assert fehl[0].actor_user_id == user.id
    assert fehl[0].payload == {"grund": "passwort_falsch"}
    assert fehl[0].ip == "127.0.0.0"  # ASGI-Testclient 127.0.0.1, auf /24 gekuerzt
    assert fehl[0].request_id
    assert len(await _eintraege(mandant.id, "login")) == 1
    # Unbekannte Adresse: kein Mandant, kein Eintrag im Mandantenprotokoll.
    async with system_session() as session:
        alle = (await session.execute(select(AuditLog).where(AuditLog.mandant_id.is_(None)))).scalars().all()
    assert alle == []

    token = ok.json()["access_token"]
    abmelden = await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(token))
    assert abmelden.status_code == 204
    assert len(await _eintraege(mandant.id, "logout_alle_geraete")) == 1


@pytest.mark.asyncio
async def test_einsicht_nur_fuer_mandant_admin_mit_filtern_und_paginierung(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    t_token = await login(client, techniker.email, "pw-123456")
    for pfad in ("", "/verifizieren", "/export.csv", "/aktionen"):
        assert (await client.get(f"/api/audit{pfad}", headers=auth_headers(t_token))).status_code == 403
    assert (await client.get("/api/audit")).status_code == 401

    objekt = uuid.uuid4()
    async with system_session() as session:
        for i in range(7):
            await audit_service.log_action(
                session,
                aktion="rechnung_versendet" if i % 2 == 0 else "zahlung_gebucht",
                mandant_id=mandant.id,
                actor_user_id=admin.id,
                entity_type="rechnung",
                entity_id=objekt if i < 3 else None,
            )

    seite1 = (await client.get("/api/audit", params={"aktion": "rechnung_", "limit": 2}, headers=auth_headers(token))).json()
    assert seite1["gesamt"] == 4 and len(seite1["eintraege"]) == 2
    seite2 = (
        await client.get("/api/audit", params={"aktion": "rechnung_", "limit": 2, "offset": 2}, headers=auth_headers(token))
    ).json()
    assert {e["id"] for e in seite1["eintraege"]}.isdisjoint({e["id"] for e in seite2["eintraege"]})
    assert seite1["eintraege"][0]["actor_name"] == "Test User"

    nach_objekt = (await client.get("/api/audit", params={"entity_id": str(objekt)}, headers=auth_headers(token))).json()
    assert nach_objekt["gesamt"] == 3
    nach_akteur = (
        await client.get("/api/audit", params={"actor_user_id": str(admin.id), "aktion": "zahlung"}, headers=auth_headers(token))
    ).json()
    assert nach_akteur["gesamt"] == 3
    zukunft = (await client.get("/api/audit", params={"von": "2999-01-01"}, headers=auth_headers(token))).json()
    assert zukunft["gesamt"] == 0
    assert (await client.get("/api/audit", params={"akteur_typ": "alien"}, headers=auth_headers(token))).status_code == 422


@pytest.mark.asyncio
async def test_csv_export_mit_formelschutz_und_selbst_protokolliert(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    boese = await make_user(mandant=mandant, role="techniker", name="=HYPERLINK(\"http://x\")")
    async with system_session() as session:
        await audit_service.log_action(
            session, aktion="test_csv", mandant_id=mandant.id, actor_user_id=boese.id, payload={"x": "=1+1"}
        )
    resp = await client.get("/api/audit/export.csv", headers=auth_headers(token))
    assert resp.status_code == 200
    text_ = resp.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text_
    assert ";=HYPERLINK" not in text_
    assert len(await _eintraege(mandant.id, "export_audit_csv")) == 1


@pytest.mark.asyncio
async def test_rechnungsereignisse_zahlung_storno_export(client, make_mandant, make_user, make_kunde):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(token)

    r = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "100"})).json()
    assert (await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})).status_code == 200
    z = await client.post(f"/api/rechnungen/{r['id']}/zahlungen", headers=h, json={"betrag": "50.00"})
    assert z.status_code == 201
    from app.models.rechnung import RechnungZahlung

    async with system_session() as session:
        zahlung = (await session.execute(select(RechnungZahlung))).scalars().first()
    assert (await client.post(f"/api/rechnungen/{r['id']}/zahlungen/{zahlung.id}/storno", headers=h)).status_code == 201
    assert (await client.post(f"/api/rechnungen/{r['id']}/storno", headers=h)).status_code == 201
    assert (await client.get("/api/rechnungen/export/csv", headers=h)).status_code == 200
    assert (await client.get("/api/auswertung/ust-va", params={"von": "2026-01-01", "bis": "2026-12-31"}, headers=h)).status_code == 200

    aktionen = [e.aktion for e in await _eintraege(mandant.id)]
    for erwartet in (
        "rechnung_erstellt",
        "rechnung_versendet",
        "zahlung_gebucht",
        "zahlung_storniert",
        "rechnung_storniert",
        "export_csv",
        "export_ustva",
    ):
        assert erwartet in aktionen, erwartet
    versand = (await _eintraege(mandant.id, "rechnung_versendet"))[0]
    assert versand.entity_id == uuid.UUID(r["id"]) and versand.payload["rechnungsnummer"] == r["rechnungsnummer"]
    # Kette bleibt durchgehend gueltig.
    assert (await client.get("/api/audit/verifizieren", headers=h)).json()["ok"] is True


@pytest.mark.asyncio
async def test_steuerdaten_aenderung_wird_mit_vorher_nachher_protokolliert(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    h = auth_headers(token)
    assert (
        await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": {"steuernummer": "12/345/67890"}})
    ).status_code == 200
    assert (
        await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": {"e_rechnung_modus": "b2b", "telefon": "123"}})
    ).status_code == 200
    eintraege = await _eintraege(mandant.id, "steuerdaten_geaendert")
    assert len(eintraege) == 2
    assert eintraege[0].payload["nachher"] == {"steuernummer": "12/345/67890"}
    assert eintraege[0].payload["vorher"] == {"steuernummer": None}
    # Nicht steuerrelevante Schluessel (telefon) tauchen nicht im Protokoll auf.
    assert "telefon" not in eintraege[1].payload["nachher"]
    assert eintraege[1].payload["nachher"]["e_rechnung_modus"] == "b2b"
