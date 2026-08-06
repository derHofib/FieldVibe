import smtplib
from email.message import EmailMessage
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models.email_log import EmailLog
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
    session: AsyncSession,
    mandant_id: UUID,
    *,
    to: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes, str] | None = None,
) -> None:
    """Verschickt eine E-Mail ueber die smtp-Integration des Mandanten.
    Wirft EmailNichtKonfiguriert, wenn keine (oder eine unvollstaendige)
    smtp-Integration hinterlegt ist -- der Aufrufer entscheidet, ob das ein
    harter Fehler ist oder (wie beim Kundenportal-Passwort-Reset) still
    geschluckt werden soll, um Rueckschluesse auf Konfigurationszustand zu
    vermeiden. attachment ist optional (Dateiname, Inhalt, Mimetype
    z.B. "application/pdf") -- fuer den Versand von Angebot/Rechnung/
    Bestellung als PDF-Anhang."""
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
    if attachment is not None:
        dateiname, inhalt, mimetype = attachment
        maintype, _, subtype = mimetype.partition("/")
        message.add_attachment(inhalt, maintype=maintype, subtype=subtype or "octet-stream", filename=dateiname)

    # smtplib ist blockierend -- in einem Thread ausfuehren, damit ein
    # langsamer/haengender SMTP-Server nicht den Event-Loop blockiert.
    await anyio.to_thread.run_sync(
        lambda: _send_blocking(host=host, port=port, user=user, password=password, message=message)
    )


async def send_email_and_log(
    session: AsyncSession,
    mandant_id: UUID,
    *,
    entity_type: str,
    entity_id: UUID,
    to: str,
    subject: str,
    body: str,
    gesendet_von: UUID | None = None,
    attachment: tuple[str, bytes, str] | None = None,
) -> EmailLog:
    """Wie send_email, schreibt aber -- egal ob Versand gelingt oder
    fehlschlaegt -- einen EmailLog-Eintrag, damit der Nutzer im Verlauf
    am Kunden/Vorgang/Dokument immer sieht, was passiert ist. Der
    Aufrufer gibt log unveraendert (inkl. status/fehlermeldung) als
    normale 201-Antwort zurueck statt bei einem Fehlschlag eine
    HTTPException zu werfen -- sonst wuerde die umgebende request-
    Transaktion (siehe app/db/session.py:tenant_session, ein einzelnes
    `async with session.begin()` je Request) beim Hochreichen der
    Exception rueckgerollt und dieser Log-Eintrag mit ihr geloescht."""
    status_wert = "gesendet"
    fehlermeldung: str | None = None
    try:
        await send_email(session, mandant_id, to=to, subject=subject, body=body, attachment=attachment)
    except EmailNichtKonfiguriert:
        status_wert = "fehler"
        fehlermeldung = "Kein SMTP-Postfach für diesen Mandanten hinterlegt (siehe Integrationen)."
    except Exception as exc:  # smtplib-Fehler: falscher Host/Login/Timeout etc.
        status_wert = "fehler"
        fehlermeldung = str(exc)

    log = EmailLog(
        mandant_id=mandant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        empfaenger=to,
        betreff=subject,
        inhalt=body,
        anhang_dateiname=attachment[0] if attachment else None,
        status=status_wert,
        fehlermeldung=fehlermeldung,
        gesendet_von=gesendet_von,
    )
    session.add(log)
    await session.flush()
    await session.refresh(log)
    return log

