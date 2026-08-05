from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.db.session import system_session
from app.models.integration import MandantIntegration
from app.models.material import Material
from tests.conftest import auth_headers, login


async def _mit_smtp_integration(mandant) -> None:
    async with system_session() as session:
        session.add(
            MandantIntegration(
                mandant_id=mandant.id,
                typ="smtp",
                config={"host": "smtp.example.de", "from_address": "bot@example.de"},
                aktiv=True,
            )
        )
        await session.commit()


async def _make_material(mandant, **kwargs) -> Material:
    async with system_session() as session:
        material = Material(
            mandant_id=mandant.id,
            bezeichnung=kwargs.pop("bezeichnung", "Kabel NYM 3x1.5"),
            einheit=kwargs.pop("einheit", "m"),
            einzelpreis=kwargs.pop("einzelpreis", Decimal("2.50")),
            **kwargs,
        )
        session.add(material)
        await session.flush()
        await session.refresh(material)
        return material


@pytest.mark.asyncio
async def test_kunde_email_wird_versendet_und_protokolliert(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _mit_smtp_integration(mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch("app.services.email_service.send_email", new_callable=AsyncMock) as mocked_send:
        resp = await client.post(
            f"/api/kunden/{kunde.id}/emails",
            headers=auth_headers(token),
            json={
                "empfaenger": "kontakt@beispielfirma.de",
                "betreff": "Terminbestaetigung",
                "inhalt": "Wir kommen wie besprochen am Montag vorbei.",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "gesendet"
    assert body["entity_type"] == "kunde"
    mocked_send.assert_called_once()
    _, kwargs = mocked_send.call_args
    assert kwargs["to"] == "kontakt@beispielfirma.de"
    assert kwargs["subject"] == "Terminbestaetigung"

    verlauf = await client.get(f"/api/kunden/{kunde.id}/emails", headers=auth_headers(token))
    assert verlauf.status_code == 200
    [eintrag] = verlauf.json()
    assert eintrag["id"] == body["id"]


@pytest.mark.asyncio
async def test_kunde_email_ohne_smtp_wird_als_fehler_protokolliert(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/kunden/{kunde.id}/emails",
        headers=auth_headers(token),
        json={
            "empfaenger": "kontakt@beispielfirma.de",
            "betreff": "Test",
            "inhalt": "Test",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "fehler"
    assert "SMTP" in body["fehlermeldung"]

    verlauf = await client.get(f"/api/kunden/{kunde.id}/emails", headers=auth_headers(token))
    [eintrag] = verlauf.json()
    assert eintrag["status"] == "fehler"
    assert "SMTP" in eintrag["fehlermeldung"]


@pytest.mark.asyncio
async def test_vorgang_email_wird_versendet_und_protokolliert(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _mit_smtp_integration(mandant)
    token = await login(client, admin.email, "pw-123456")

    with patch("app.services.email_service.send_email", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/vorgaenge/{vorgang.id}/emails",
            headers=auth_headers(token),
            json={
                "empfaenger": "kunde@beispielfirma.de",
                "betreff": "Statusupdate",
                "inhalt": "Der Vorgang ist in Bearbeitung.",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["entity_type"] == "vorgang"

    verlauf = await client.get(f"/api/vorgaenge/{vorgang.id}/emails", headers=auth_headers(token))
    assert len(verlauf.json()) == 1


@pytest.mark.asyncio
async def test_angebot_pdf_wird_als_anhang_versendet(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _mit_smtp_integration(mandant)
    token = await login(client, admin.email, "pw-123456")

    angebot_resp = await client.post(
        "/api/angebote",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "positionen": [
                {"beschreibung": "Installation", "menge": "2", "einheit": "Std", "einzelpreis": "80.00"},
            ],
        },
    )
    angebot_id = angebot_resp.json()["id"]

    with patch("app.services.email_service.send_email", new_callable=AsyncMock) as mocked_send:
        resp = await client.post(
            f"/api/angebote/{angebot_id}/email",
            headers=auth_headers(token),
            json={"empfaenger": "kunde@beispielfirma.de"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["anhang_dateiname"].endswith(".pdf")
    mocked_send.assert_called_once()
    _, kwargs = mocked_send.call_args
    dateiname, inhalt, mimetype = kwargs["attachment"]
    assert dateiname == body["anhang_dateiname"]
    assert mimetype == "application/pdf"
    assert inhalt.startswith(b"%PDF")

    verlauf = await client.get(f"/api/angebote/{angebot_id}/emails", headers=auth_headers(token))
    assert len(verlauf.json()) == 1


@pytest.mark.asyncio
async def test_rechnung_pdf_wird_als_anhang_versendet(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _mit_smtp_integration(mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "500.00"},
    )
    rechnung_id = rechnung_resp.json()["id"]

    with patch("app.services.email_service.send_email", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/rechnungen/{rechnung_id}/email",
            headers=auth_headers(token),
            json={"empfaenger": "kunde@beispielfirma.de"},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "gesendet"


@pytest.mark.asyncio
async def test_bestellung_pdf_wird_als_anhang_versendet(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    await _mit_smtp_integration(mandant)
    token = await login(client, admin.email, "pw-123456")

    lieferant_resp = await client.post(
        "/api/lieferanten", headers=auth_headers(token), json={"name": "Sonepar", "email": "sonepar@beispiel.de"}
    )
    lieferant_id = lieferant_resp.json()["id"]

    bedarf_resp = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "10"},
    )

    bestellung_resp = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf_resp.json()["id"]], "lieferant_id": lieferant_id},
    )
    bestellung_id = bestellung_resp.json()["id"]

    with patch("app.services.email_service.send_email", new_callable=AsyncMock):
        resp = await client.post(
            f"/api/bestellungen/{bestellung_id}/email",
            headers=auth_headers(token),
            json={"empfaenger": "sonepar@beispiel.de"},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "gesendet"
