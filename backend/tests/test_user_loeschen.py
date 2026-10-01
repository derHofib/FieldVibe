import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.services.user_anonymisierung_service import ist_anonymisiert
from tests.conftest import auth_headers, login


async def _zeiterfassung_anlegen(mandant, user) -> uuid.UUID:
    async with system_session() as session:
        eintrag = Zeiterfassung(
            mandant_id=mandant.id,
            techniker_id=user.id,
            start_at=datetime.now(UTC),
            ende_at=datetime.now(UTC),
            kategorie="verwaltung",
        )
        session.add(eintrag)
        await session.flush()
        return eintrag.id


async def _user_laden(user_id) -> User | None:
    async with system_session() as session:
        return await session.get(User, user_id)


async def _admin_token(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    return mandant, admin, await login(client, admin.email, "pw-123456")


@pytest.mark.asyncio
async def test_nutzer_ohne_daten_wird_echt_geloescht(client, make_mandant, make_user):
    mandant, _, token = await _admin_token(client, make_mandant, make_user)
    opfer = await make_user(mandant=mandant, role="techniker")

    resp = await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))

    assert resp.status_code == 204
    assert await _user_laden(opfer.id) is None


@pytest.mark.asyncio
async def test_nutzer_mit_daten_wird_anonymisiert(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    opfer = await make_user(mandant=mandant, role="techniker", name="Erika Muster", password="altes-pw-123")
    alte_email = opfer.email
    zeit_id = await _zeiterfassung_anlegen(mandant, opfer)
    kunde = await make_kunde(mandant=mandant)
    offen = await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=opfer.id)
    erledigt = await make_vorgang(
        mandant=mandant, kunde=kunde, zugewiesener_user_id=opfer.id, status="abgeschlossen"
    )
    async with system_session() as session:
        session.add(KundeZuweisung(mandant_id=mandant.id, kunde_id=kunde.id, user_id=opfer.id))

    resp = await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    user = await _user_laden(opfer.id)
    assert user is not None and ist_anonymisiert(user)
    assert user.name == "Gelöschter Nutzer"
    assert user.email != alte_email
    assert user.email.endswith("@invalid.fieldvibe")
    assert user.aktiv is False
    assert user.avatar_url is None

    # Login mit altem und neuem Namen schlaegt fehl (ohne 500).
    for email in (alte_email, user.email):
        login_resp = await client.post(
            "/api/auth/login", json={"email": email, "password": "altes-pw-123"}
        )
        assert login_resp.status_code == 401

    async with system_session() as session:
        assert await session.get(Zeiterfassung, zeit_id) is not None
        assert (await session.get(Vorgang, offen.id)).zugewiesener_user_id is None
        assert (await session.get(Vorgang, erledigt.id)).zugewiesener_user_id == opfer.id
        zuweisungen = await session.execute(select(KundeZuweisung).where(KundeZuweisung.user_id == opfer.id))
        assert zuweisungen.first() is None

    liste = await client.get("/api/users?versteckte=1", headers=auth_headers(token))
    assert str(opfer.id) not in {u["id"] for u in liste.json()}

    # Nochmal loeschen/aendern ist nicht moeglich.
    assert (await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))).status_code == 404
    patch = await client.patch(f"/api/users/{opfer.id}", headers=auth_headers(token), json={"aktiv": True})
    assert patch.status_code == 404


@pytest.mark.asyncio
async def test_email_nach_anonymisierung_wieder_einladbar(client, make_mandant, make_user):
    mandant, _, token = await _admin_token(client, make_mandant, make_user)
    opfer = await make_user(mandant=mandant, role="techniker")
    await _zeiterfassung_anlegen(mandant, opfer)

    assert (await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))).status_code == 204

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": opfer.email, "role": "mandant_admin"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_audit_log_ohne_alte_email(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    opfer = await make_user(mandant=mandant, role="techniker", email="geheim.person@example.de")
    await _zeiterfassung_anlegen(mandant, opfer)

    assert (await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))).status_code == 204

    async with system_session() as session:
        eintraege = (
            await session.execute(select(AuditLog).where(AuditLog.entity_id == opfer.id))
        ).scalars().all()
    anonymisiert = [e for e in eintraege if e.aktion == "user_anonymisiert"]
    assert len(anonymisiert) == 1
    assert anonymisiert[0].actor_user_id == admin.id
    assert anonymisiert[0].payload == {"role": "custom"}
    assert all("geheim.person" not in str(e.payload) for e in eintraege)


@pytest.mark.asyncio
async def test_echtes_loeschen_loggt_user_geloescht(client, make_mandant, make_user):
    mandant, _, token = await _admin_token(client, make_mandant, make_user)
    opfer = await make_user(mandant=mandant, role="techniker")
    await client.delete(f"/api/users/{opfer.id}", headers=auth_headers(token))
    async with system_session() as session:
        aktionen = (
            await session.execute(select(AuditLog.aktion).where(AuditLog.entity_id == opfer.id))
        ).scalars().all()
    assert aktionen == ["user_geloescht"]


@pytest.mark.asyncio
async def test_rechte_und_schutzregeln(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    papierkorb = await make_user(mandant=mandant, role="loesch_operativ")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")

    # Sich selbst nicht; letzter mandant_admin ist zugleich man selbst.
    assert (await client.delete(f"/api/users/{admin.id}", headers=auth_headers(token))).status_code == 400
    # Papierkorb-Accounts nicht als mandant_admin; super_admin ist per RLS gar nicht sichtbar (404).
    assert (await client.delete(f"/api/users/{papierkorb.id}", headers=auth_headers(token))).status_code == 403
    assert (await client.delete(f"/api/users/{super_admin.id}", headers=auth_headers(token))).status_code == 404

    # Zweiter Admin: der letzte Admin ist geschuetzt, solange nur ein anderer existiert.
    zweiter = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token2 = await login(client, zweiter.email, "pw-123456")
    assert (await client.delete(f"/api/users/{admin.id}", headers=auth_headers(token2))).status_code == 204
    # Jetzt ist zweiter allein -- ein super_admin darf trotzdem nicht den letzten Admin loeschen.
    sa_token = await login(client, super_admin.email, "pw-123456")
    resp = await client.delete(f"/api/users/{zweiter.id}", headers=auth_headers(sa_token))
    assert resp.status_code == 400

    # super_admin darf Papierkorb-Account loeschen.
    assert (await client.delete(f"/api/users/{papierkorb.id}", headers=auth_headers(sa_token))).status_code == 204
    # Letzter super_admin ist geschuetzt (hier: zugleich man selbst).
    assert (await client.delete(f"/api/users/{super_admin.id}", headers=auth_headers(sa_token))).status_code == 400


@pytest.mark.asyncio
async def test_super_admin_darf_anderen_super_admin_loeschen(client, make_user):
    eins = await make_user(mandant=None, role="super_admin", password="pw-123456")
    zwei = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, eins.email, "pw-123456")
    assert (await client.delete(f"/api/users/{zwei.id}", headers=auth_headers(token))).status_code == 204


@pytest.mark.asyncio
async def test_liste_ohne_super_admin_und_papierkorb_versteckt(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    papierkorb = await make_user(mandant=mandant, role="loesch_operativ", name="Papierkorb")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")

    ids = {u["id"] for u in (await client.get("/api/users", headers=auth_headers(token))).json()}
    assert str(admin.id) in ids
    assert str(papierkorb.id) not in ids
    assert str(super_admin.id) not in ids

    ids = {u["id"] for u in (await client.get("/api/users?versteckte=1", headers=auth_headers(token))).json()}
    assert str(papierkorb.id) in ids
    assert str(super_admin.id) not in ids

    # Plattform-Kontext sieht super_admins weiterhin.
    sa_token = await login(client, super_admin.email, "pw-123456")
    ids = {u["id"] for u in (await client.get("/api/users", headers=auth_headers(sa_token))).json()}
    assert str(super_admin.id) in ids


@pytest.mark.asyncio
async def test_fremder_mandant_liefert_404(client, make_mandant, make_user):
    _, _, token = await _admin_token(client, make_mandant, make_user)
    fremd = await make_mandant(name="Fremd")
    fremder = await make_user(mandant=fremd, role="techniker")
    resp = await client.delete(f"/api/users/{fremder.id}", headers=auth_headers(token))
    assert resp.status_code == 404
    assert await _user_laden(fremder.id) is not None
