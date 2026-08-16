from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.db.session import system_session, tenant_session
from app.models.plattform_integration import PlattformIntegration
from app.services.email_service import send_email
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_super_admin_kann_plattform_smtp_anlegen_und_pflegen(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    create = await client.post(
        "/api/plattform/integrationen",
        headers=auth_headers(token),
        json={
            "typ": "smtp",
            "config": {"host": "smtp.fieldvibe.de", "port": 587, "from_address": "account@fieldvibe.de"},
            "secret": "geheim",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["hat_secret"] is True
    integration_id = body["id"]

    list_resp = await client.get("/api/plattform/integrationen", headers=auth_headers(token))
    assert len(list_resp.json()) == 1

    update = await client.patch(
        f"/api/plattform/integrationen/{integration_id}",
        headers=auth_headers(token),
        json={"aktiv": False},
    )
    assert update.status_code == 200
    assert update.json()["aktiv"] is False

    delete = await client.delete(
        f"/api/plattform/integrationen/{integration_id}", headers=auth_headers(token)
    )
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_mandant_admin_hat_keinen_zugriff_auf_plattform_integrationen(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    assert (await client.get("/api/plattform/integrationen", headers=auth_headers(token))).status_code == 403
    assert (
        await client.post(
            "/api/plattform/integrationen",
            headers=auth_headers(token),
            json={"typ": "smtp", "config": {"host": "x", "from_address": "x@x.de"}},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_plattform_integration_ist_fuer_mandanten_session_lesbar_aber_nicht_schreibbar(
    make_mandant,
):
    """Direkter DB-Test der RLS-Policies: eine ganz normale
    tenant_session (nicht super_admin) muss die Zeile lesen koennen --
    genau das braucht send_email() als Fallback fuer jeden Mandanten --
    darf sie aber nicht selbst anlegen oder aendern."""
    mandant = await make_mandant()
    async with system_session() as session:
        integration = PlattformIntegration(
            typ="smtp", config={"host": "smtp.fieldvibe.de", "from_address": "account@fieldvibe.de"}
        )
        session.add(integration)
        await session.flush()
        integration_id = integration.id

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        result = await session.execute(
            select(PlattformIntegration).where(PlattformIntegration.id == integration_id)
        )
        assert result.scalar_one_or_none() is not None

    # Separater Block: die gesamte Schreiboperation muss an der RLS-Policy
    # scheitern (WITH CHECK erfordert is_super_admin) -- in einem eigenen
    # "with pytest.raises", damit eine fehlgeschlagene Transaktion nicht
    # den obigen Lese-Assert mitreisst oder verschluckt.
    with pytest.raises(Exception):
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            gelesen = await session.get(PlattformIntegration, integration_id)
            gelesen.aktiv = False
            await session.flush()


@pytest.mark.asyncio
async def test_send_email_nutzt_plattform_integration_wenn_kein_mandanten_smtp(make_mandant):
    mandant = await make_mandant(name="Elektro Müller GmbH")
    async with system_session() as session:
        session.add(
            PlattformIntegration(
                typ="smtp",
                config={"host": "smtp.fieldvibe.de", "port": 2525, "from_address": "account@fieldvibe.de"},
                aktiv=True,
            )
        )
        await session.flush()

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        async with system_session() as session:
            await send_email(session, mandant.id, to="kunde@example.de", subject="Test", body="Hallo")

    smtp_cls.assert_called_once_with("smtp.fieldvibe.de", 2525, timeout=10)
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["From"] == "Elektro Müller GmbH via FieldVibe <account@fieldvibe.de>"
