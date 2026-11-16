import dataclasses
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.kundenportal import KundenportalZugang
from app.services import system_lookups


def _ist_schmal(wert) -> bool:
    return dataclasses.is_dataclass(wert) and not hasattr(wert, "_sa_instance_state")


@pytest.mark.asyncio
async def test_lookups_liefern_schmale_werte_statt_orm_objekten(make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")

    login = await system_lookups.user_lookup_by_email(user.email.upper())
    kern = await system_lookups.user_kern_by_id(user.id, grund="test")
    token = await system_lookups.user_token_status(user.id)
    mandant_kern = await system_lookups.mandant_kern_lookup(mandant.id)

    for wert in (login, kern, token, mandant_kern):
        assert _ist_schmal(wert)
    assert login.id == user.id and login.mandant_id == mandant.id and login.aktiv
    assert login.passwort_hash == user.password_hash
    assert {f.name for f in dataclasses.fields(login)} == {"id", "mandant_id", "passwort_hash", "aktiv"}
    assert kern.email == user.email and kern.token_version == 0
    assert not hasattr(kern, "passwort_hash")
    assert mandant_kern.name == mandant.name


@pytest.mark.asyncio
async def test_portal_lookups_liefern_schmale_werte(make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    async with system_session(grund="test") as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email="portal@example.de",
            password_hash="x",
            name="Portal",
        )
        session.add(zugang)
        await session.flush()

    gefunden = await system_lookups.kundenzugang_by_email("Portal@Example.de")
    link = await system_lookups.kunde_link_lookup(kunde.portal_slug, grund="test")

    assert _ist_schmal(gefunden) and gefunden.kunde_id == kunde.id and gefunden.partner_id is None
    assert gefunden.mandant_id == mandant.id
    assert _ist_schmal(link) and link.mandant_aktiv and link.mandant_name == mandant.name


@pytest.mark.asyncio
async def test_login_schreibt_audit_unter_tenant_kontext(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")

    aufrufe: list[dict] = []
    original = db_session.tenant_session

    @asynccontextmanager
    async def spion(**kwargs):
        aufrufe.append(kwargs)
        async with original(**kwargs) as session:
            yield session

    monkeypatch.setattr(system_lookups, "tenant_session", spion)

    resp = await client.post("/api/auth/login", json={"email": user.email, "password": "korrekt-123"})

    assert resp.status_code == 200
    assert aufrufe == [{"mandant_id": mandant.id}]
    async with system_session(grund="test") as session:
        eintraege = (
            await session.execute(
                select(AuditLog).where(AuditLog.aktion == "login", AuditLog.actor_user_id == user.id)
            )
        ).scalars().all()
    assert len(eintraege) == 1 and eintraege[0].mandant_id == mandant.id


@pytest.mark.asyncio
async def test_super_admin_login_ohne_mandant_funktioniert(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="korrekt-123")

    resp = await client.post("/api/auth/login", json={"email": admin.email, "password": "korrekt-123"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unbekannte_email_liefert_none_ohne_exception(client):
    assert await system_lookups.user_lookup_by_email("niemand@example.de") is None
    assert await system_lookups.user_kern_by_email("niemand@example.de") is None
    assert await system_lookups.kundenzugang_by_email("niemand@example.de") is None
    assert await system_lookups.partnerzugang_by_email("niemand@example.de") is None
    assert await system_lookups.kunde_link_lookup("gibt-es-nicht", grund="test") is None

    for pfad in ("/api/auth/login", "/api/kundenportal/auth/login", "/api/partnerportal/auth/login"):
        resp = await client.post(pfad, json={"email": "niemand@example.de", "password": "egal-12345"})
        assert resp.status_code == 401
