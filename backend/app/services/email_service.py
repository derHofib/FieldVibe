import smtplib
from email.message import EmailMessage
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models.integration import MandantIntegration


class EmailNichtKonfiguriert(Exception):
    """Der Mandant hat keine aktive smtp-Integration mit den noetigen
    Feldern (host, from_address) hinterlegt -- siehe
    app/api/routes/integrationen.py."""


async def _get_smtp_integration(session: AsyncSession, mandant_id: UUID) -> MandantIntegration:
    result = await session.execute(
        select(MandantIntegration).where(
            MandantIntegration.mandant_id == mandant_id,
            MandantIntegration.typ == "smtp",
            MandantIntegration.aktiv.is_(True),
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise EmailNichtKonfiguriert()
    return integration


def _send_blocking(*, host: str, port: int, user: str | None, password: str | None, message: EmailMessage) -> None:
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)


async def send_email(
    session: AsyncSession, mandant_id: UUID, *, to: str, subject: str, body: str
) -> None:
    """Verschickt eine E-Mail ueber die smtp-Integration des Mandanten.
    Wirft EmailNichtKonfiguriert, wenn keine (oder eine unvollstaendige)
    smtp-Integration hinterlegt ist -- der Aufrufer entscheidet, ob das ein
    harter Fehler ist oder (wie beim Kundenportal-Passwort-Reset) still
    geschluckt werden soll, um Rueckschluesse auf Konfigurationszustand zu
    vermeiden."""
    integration = await _get_smtp_integration(session, mandant_id)
    config = integration.config
    host = config.get("host")
    from_address = config.get("from_address") or config.get("user")
    if not host or not from_address:
        raise EmailNichtKonfiguriert()
    port = int(config.get("port", 587))
    user = config.get("user")
    password = decrypt_secret(integration.secret_ref) if integration.secret_ref else None

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to
    message.set_content(body)

    # smtplib ist blockierend -- in einem Thread ausfuehren, damit ein
    # langsamer/haengender SMTP-Server nicht den Event-Loop blockiert.
    await anyio.to_thread.run_sync(
        lambda: _send_blocking(host=host, port=port, user=user, password=password, message=message)
    )
