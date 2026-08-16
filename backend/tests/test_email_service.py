from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.db.session import system_session
from app.models.integration import MandantIntegration
from app.services.email_service import EmailNichtKonfiguriert, send_email
from tests.conftest import auth_headers, login


@pytest.fixture
def global_smtp(monkeypatch):
    """Setzt GLOBAL_SMTP_* fuer die Dauer eines Tests -- get_settings() ist
    lru_cache-basiert (ein Singleton), also direkt am Objekt patchen statt
    ueber Umgebungsvariablen (die kaemen zu spaet an)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "global_smtp_host", "smtp.fieldvibe.de")
    monkeypatch.setattr(settings, "global_smtp_port", 2525)
    monkeypatch.setattr(settings, "global_smtp_user", "global-bot")
    monkeypatch.setattr(settings, "global_smtp_password", "global-pw")
    monkeypatch.setattr(settings, "global_smtp_from_address", "account@fieldvibe.de")
    return settings


async def _make_smtp_integration(mandant, **overrides) -> MandantIntegration:
    async with system_session() as session:
        integration = MandantIntegration(
            mandant_id=mandant.id,
            typ="smtp",
            config={
                "host": "smtp.example.de",
                "port": 587,
                "user": "bot@example.de",
                "from_address": "bot@example.de",
                **overrides,
            },
            secret_ref=None,
            aktiv=True,
        )
        session.add(integration)
        await session.flush()
        await session.refresh(integration)
        return integration


@pytest.mark.asyncio
async def test_send_email_uses_configured_smtp(make_mandant):
    mandant = await make_mandant()
    await _make_smtp_integration(mandant)

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        async with system_session() as session:
            await send_email(
                session, mandant.id, to="kunde@example.de", subject="Test", body="Hallo"
            )

    smtp_cls.assert_called_once_with("smtp.example.de", 587, timeout=10)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.send_message.assert_called_once()
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["To"] == "kunde@example.de"
    assert sent_message["From"] == "bot@example.de"
    assert sent_message["Subject"] == "Test"


@pytest.mark.asyncio
async def test_send_email_with_html_body_sends_multipart_alternative(make_mandant):
    mandant = await make_mandant()
    await _make_smtp_integration(mandant)

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance):
        async with system_session() as session:
            await send_email(
                session,
                mandant.id,
                to="kunde@example.de",
                subject="Test",
                body="Nur-Text-Fallback",
                html_body="<html><body><p>Hallo</p></body></html>",
            )

    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message.is_multipart()
    parts = list(sent_message.walk())
    plain_parts = [p for p in parts if p.get_content_type() == "text/plain"]
    html_parts = [p for p in parts if p.get_content_type() == "text/html"]
    assert len(plain_parts) == 1
    assert len(html_parts) == 1
    assert "Nur-Text-Fallback" in plain_parts[0].get_content()
    assert "<p>Hallo</p>" in html_parts[0].get_content()


@pytest.mark.asyncio
async def test_send_email_raises_when_no_smtp_configured(make_mandant):
    mandant = await make_mandant()

    with pytest.raises(EmailNichtKonfiguriert):
        async with system_session() as session:
            await send_email(session, mandant.id, to="x@example.de", subject="s", body="b")


@pytest.mark.asyncio
async def test_send_email_raises_when_smtp_config_incomplete(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        integration = MandantIntegration(
            mandant_id=mandant.id, typ="smtp", config={}, aktiv=True
        )
        session.add(integration)
        await session.commit()

    with pytest.raises(EmailNichtKonfiguriert):
        async with system_session() as session:
            await send_email(session, mandant.id, to="x@example.de", subject="s", body="b")


@pytest.mark.asyncio
async def test_send_email_faellt_auf_globalen_smtp_zurueck(global_smtp, make_mandant):
    mandant = await make_mandant(name="Elektro Müller GmbH")
    # Bewusst keine eigene smtp-Integration fuer diesen Mandanten.

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        async with system_session() as session:
            await send_email(session, mandant.id, to="kunde@example.de", subject="Test", body="Hallo")

    smtp_cls.assert_called_once_with("smtp.fieldvibe.de", 2525, timeout=10)
    smtp_instance.login.assert_called_once_with("global-bot", "global-pw")
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["From"] == 'Elektro Müller GmbH via FieldVibe <account@fieldvibe.de>'


@pytest.mark.asyncio
async def test_mandanten_eigene_smtp_hat_vorrang_vor_global(global_smtp, make_mandant):
    mandant = await make_mandant(name="Elektro Müller GmbH")
    await _make_smtp_integration(mandant)

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        async with system_session() as session:
            await send_email(session, mandant.id, to="kunde@example.de", subject="Test", body="Hallo")

    smtp_cls.assert_called_once_with("smtp.example.de", 587, timeout=10)
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["From"] == "bot@example.de"


@pytest.mark.asyncio
async def test_send_email_logs_in_when_secret_present(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/integrationen",
        headers=auth_headers(token),
        json={
            "typ": "smtp",
            "config": {"host": "smtp.example.de", "port": 587, "user": "bot@example.de", "from_address": "bot@example.de"},
            "secret": "smtp-passwort",
        },
    )

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_instance):
        async with system_session() as session:
            await send_email(session, mandant.id, to="kunde@example.de", subject="s", body="b")

    smtp_instance.login.assert_called_once_with("bot@example.de", "smtp-passwort")
