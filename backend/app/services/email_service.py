import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.integration import MandantIntegration
from app.models.mandant import Mandant


class EmailNichtKonfiguriert(Exception):
    """Weder eine aktive smtp-Integration des Mandanten noch ein globaler
    Plattform-Mailversand (GLOBAL_SMTP_*) ist konfiguriert -- siehe
    _resolve_smtp() unten."""


@dataclass
class _SmtpVerbindung:
    host: str
    port: int
    user: str | None
    password: str | None
    from_address: str
    ist_global: bool


async def _resolve_smtp(session: AsyncSession, mandant_id: UUID) -> _SmtpVerbindung:
    """Eigene smtp-Integration des Mandanten hat immer Vorrang; ist keine
    (vollstaendige) hinterlegt, greift der globale Plattform-Mailversand
    als Fallback (GLOBAL_SMTP_* in den Settings) -- damit Einladungen und
    Passwort-Reset-Mails schon vor der ersten eigenen SMTP-Konfiguration
    eines Mandanten funktionieren, statt an einem Henne-Ei-Problem beim
    Onboarding zu scheitern."""
    result = await session.execute(
        select(MandantIntegration).where(
            MandantIntegration.mandant_id == mandant_id,
            MandantIntegration.typ == "smtp",
            MandantIntegration.aktiv.is_(True),
        )
    )
    integration = result.scalar_one_or_none()
    if integration is not None:
        config = integration.config
        host = config.get("host")
        from_address = config.get("from_address") or config.get("user")
        if host and from_address:
            return _SmtpVerbindung(
                host=host,
                port=int(config.get("port", 587)),
                user=config.get("user"),
                password=decrypt_secret(integration.secret_ref) if integration.secret_ref else None,
                from_address=from_address,
                ist_global=False,
            )

    settings = get_settings()
    if settings.global_smtp_host and settings.global_smtp_from_address:
        return _SmtpVerbindung(
            host=settings.global_smtp_host,
            port=settings.global_smtp_port,
            user=settings.global_smtp_user,
            password=settings.global_smtp_password,
            from_address=settings.global_smtp_from_address,
            ist_global=True,
        )

    raise EmailNichtKonfiguriert()


def _send_blocking(*, host: str, port: int, user: str | None, password: str | None, message: EmailMessage) -> None:
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)


async def send_email(
    session: AsyncSession, mandant_id: UUID, *, to: str, subject: str, body: str, html_body: str | None = None
) -> None:
    """Verschickt eine E-Mail ueber die smtp-Integration des Mandanten,
    oder -- falls keine hinterlegt ist -- ueber den globalen
    Plattform-Mailversand (siehe _resolve_smtp). Wirft
    EmailNichtKonfiguriert, wenn auch das nicht konfiguriert ist; der
    Aufrufer entscheidet, ob das ein harter Fehler ist oder (wie beim
    Kundenportal-Passwort-Reset) still geschluckt werden soll, um
    Rueckschluesse auf Konfigurationszustand zu vermeiden.

    `body` ist immer Pflicht und bleibt die einzige Version fuer Clients
    ohne HTML-Darstellung. Wird zusaetzlich `html_body` angegeben, verschickt
    add_alternative() eine multipart/alternative-Mail -- der Text-Teil zuerst
    (Fallback), der HTML-Teil danach (von Clients bevorzugt, die beides
    koennen; siehe app/services/einladung_service.py)."""
    verbindung = await _resolve_smtp(session, mandant_id)

    from_address = verbindung.from_address
    if verbindung.ist_global:
        # Beim globalen Fallback traegt der Anzeigename den Mandanten,
        # nicht die Absenderadresse selbst -- die muss auf der Domain
        # bleiben, fuer die FieldVibe tatsaechlich SPF/DKIM eingerichtet
        # hat, sonst wirkt die Mail wie Spoofing statt wie eine echte
        # Nachricht vom Betrieb.
        mandant = await session.get(Mandant, mandant_id)
        if mandant is not None:
            from_address = formataddr((f"{mandant.name} via FieldVibe", verbindung.from_address))

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")

    # smtplib ist blockierend -- in einem Thread ausfuehren, damit ein
    # langsamer/haengender SMTP-Server nicht den Event-Loop blockiert.
    await anyio.to_thread.run_sync(
        lambda: _send_blocking(
            host=verbindung.host, port=verbindung.port, user=verbindung.user,
            password=verbindung.password, message=message,
        )
    )
