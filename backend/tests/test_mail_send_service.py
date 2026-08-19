from unittest.mock import MagicMock, patch

import pytest

from app.core.security import encrypt_secret
from app.models.mail_account import MailAccount
from app.services.mail_send_service import sende_nachricht


def _account(**overrides) -> MailAccount:
    account = MailAccount(
        smtp_host="smtp.example.de",
        smtp_port=587,
        smtp_verschluesselung="starttls",
        smtp_benutzername="technik@example.de",
        email_adresse="technik@example.de",
        passwort_verschluesselt=encrypt_secret("geheim"),
        signatur=None,
    )
    for key, value in overrides.items():
        setattr(account, key, value)
    return account


@pytest.mark.asyncio
async def test_sende_nachricht_starttls_login_und_envelope():
    account = _account()
    smtp_instance = MagicMock()
    with patch("app.services.mail_send_service.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        await sende_nachricht(
            account, an=["kunde@example.de"], cc=["kollege@example.de"], bcc=["chef@example.de"],
            betreff="Terminvorschlag", text="Wie besprochen.",
        )

    smtp_cls.assert_called_once_with("smtp.example.de", 587, timeout=20)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("technik@example.de", "geheim")
    smtp_instance.send_message.assert_called_once()

    gesendete_nachricht, kwargs = smtp_instance.send_message.call_args
    nachricht = gesendete_nachricht[0]
    assert nachricht["From"] == "technik@example.de"
    assert nachricht["To"] == "kunde@example.de"
    assert nachricht["Cc"] == "kollege@example.de"
    # Bcc darf NICHT als Kopfzeile auftauchen -- sonst saehen alle anderen
    # Empfaenger, wer verdeckt mitgelesen hat. Muss trotzdem tatsaechlich
    # zugestellt werden, also im expliziten SMTP-Envelope stehen.
    assert "Bcc" not in nachricht
    assert set(kwargs["to_addrs"]) == {"kunde@example.de", "kollege@example.de", "chef@example.de"}


@pytest.mark.asyncio
async def test_sende_nachricht_ssl_verwendet_smtp_ssl():
    account = _account(smtp_verschluesselung="ssl", smtp_port=465)
    smtp_instance = MagicMock()
    with patch("app.services.mail_send_service.smtplib.SMTP_SSL", return_value=smtp_instance) as smtp_cls:
        await sende_nachricht(account, an=["kunde@example.de"], betreff="X", text="Y")

    smtp_cls.assert_called_once_with("smtp.example.de", 465, timeout=20)
    smtp_instance.starttls.assert_not_called()


@pytest.mark.asyncio
async def test_sende_nachricht_haengt_signatur_an():
    account = _account(signatur="Mit freundlichen Grüßen\nTechnik-Team")
    smtp_instance = MagicMock()
    with patch("app.services.mail_send_service.smtplib.SMTP", return_value=smtp_instance):
        await sende_nachricht(account, an=["kunde@example.de"], betreff="X", text="Hallo!")

    nachricht = smtp_instance.send_message.call_args[0][0]
    body = nachricht.get_content()
    assert "Hallo!" in body
    assert "Technik-Team" in body


@pytest.mark.asyncio
async def test_sende_nachricht_setzt_threading_header():
    account = _account()
    smtp_instance = MagicMock()
    with patch("app.services.mail_send_service.smtplib.SMTP", return_value=smtp_instance):
        await sende_nachricht(
            account, an=["kunde@example.de"], betreff="Re: Anfrage", text="Antwort",
            in_reply_to="<original@kunde.de>", references="<original@kunde.de>",
        )

    nachricht = smtp_instance.send_message.call_args[0][0]
    assert nachricht["In-Reply-To"] == "<original@kunde.de>"
    assert nachricht["References"] == "<original@kunde.de>"
