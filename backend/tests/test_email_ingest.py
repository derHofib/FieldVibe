from email.message import EmailMessage

import pytest
from sqlalchemy import select

from app.core.security import encrypt_secret
from app.db.session import system_session
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.integration import MandantIntegration
from app.models.notification import Notification
from app.services import email_ingest_service


def _rfc822_mit_pdf(*, absender: str, betreff: str, dateiname: str = "rechnung.pdf") -> bytes:
    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = "rechnung@mandant.de"
    nachricht["Subject"] = betreff
    nachricht.set_content("Siehe Anhang.")
    nachricht.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename=dateiname)
    return bytes(nachricht)


def _rfc822_ohne_anhang(*, absender: str, betreff: str) -> bytes:
    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = "rechnung@mandant.de"
    nachricht["Subject"] = betreff
    nachricht.set_content("Kein Anhang, z.B. Newsletter.")
    return bytes(nachricht)


@pytest.mark.asyncio
async def test_run_email_ingest_legt_entwurf_pro_pdf_anhang_an(make_mandant, monkeypatch):
    mandant = await make_mandant()

    async with system_session() as session:
        integration = MandantIntegration(
            mandant_id=mandant.id,
            typ="imap",
            config={"host": "imap.example.de", "port": 993, "user": "rechnung@example.de", "mailbox": "INBOX"},
            secret_ref=encrypt_secret("postfach-passwort"),
            aktiv=True,
        )
        session.add(integration)
        await session.flush()
        integration_id = integration.id

    nachrichten = [
        _rfc822_mit_pdf(absender="Sonepar <buchhaltung@sonepar.de>", betreff="Ihre Rechnung RE-1"),
        _rfc822_ohne_anhang(absender="newsletter@irgendwer.de", betreff="Angebote der Woche"),
    ]

    def fake_fetch(integration_obj):
        assert integration_obj.id == integration_id
        return nachrichten, 42

    monkeypatch.setattr(email_ingest_service, "_fetch_neue_nachrichten", fake_fetch)

    ergebnis = await email_ingest_service.run_email_ingest([mandant.id])
    assert ergebnis["neue_entwuerfe"] == 1
    assert ergebnis["fehler"] == 0

    async with system_session() as session:
        entwuerfe = (
            (await session.execute(select(Eingangsrechnung).where(Eingangsrechnung.mandant_id == mandant.id)))
            .scalars()
            .all()
        )
        assert len(entwuerfe) == 1
        entwurf = entwuerfe[0]
        assert entwurf.status == "entwurf"
        assert entwurf.erstellt_von is None
        assert entwurf.lieferant_name == "Sonepar"
        assert entwurf.email_absender == "buchhaltung@sonepar.de"
        assert entwurf.email_betreff == "Ihre Rechnung RE-1"
        assert entwurf.beleg_object_key is not None

        aktualisierte_integration = await session.get(MandantIntegration, integration_id)
        assert aktualisierte_integration.config["last_uid"] == 42


@pytest.mark.asyncio
async def test_run_email_ingest_ohne_aktive_integration_tut_nichts(make_mandant):
    mandant = await make_mandant()
    ergebnis = await email_ingest_service.run_email_ingest([mandant.id])
    assert ergebnis == {"neue_entwuerfe": 0, "fehler": 0}


def test_pdf_anhaenge_ignoriert_nicht_pdf_dateien():
    nachricht = EmailMessage()
    nachricht["From"] = "a@b.de"
    nachricht.set_content("Text")
    nachricht.add_attachment(b"binaerkram", maintype="application", subtype="octet-stream", filename="setup.exe")
    nachricht.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="beleg.pdf")

    anhaenge = email_ingest_service._pdf_anhaenge(nachricht)
    assert len(anhaenge) == 1
    assert anhaenge[0][0] == "beleg.pdf"
