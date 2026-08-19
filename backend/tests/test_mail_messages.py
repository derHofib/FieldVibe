import pytest

from app.core.security import encrypt_secret
from app.db.session import system_session
from app.models.mail_account import MailAccount
from app.models.mail_attachment import MailAttachment
from app.models.mail_folder import MailFolder
from app.models.mail_message import MailMessage
from tests.conftest import auth_headers, login


async def _account_und_ordner(mandant, user) -> tuple[MailAccount, MailFolder]:
    async with system_session() as session:
        account = MailAccount(
            mandant_id=mandant.id,
            user_id=user.id,
            name="Testpostfach",
            email_adresse="technik@example.de",
            imap_host="imap.example.de",
            imap_port=993,
            imap_verschluesselung="ssl",
            imap_benutzername="technik@example.de",
            smtp_host="smtp.example.de",
            smtp_port=587,
            smtp_verschluesselung="starttls",
            smtp_benutzername="technik@example.de",
            passwort_verschluesselt=encrypt_secret("geheim"),
            signatur="Mit freundlichen Grüßen\nTechnik-Team",
        )
        session.add(account)
        await session.flush()

        ordner = MailFolder(
            mandant_id=mandant.id, mail_account_id=account.id, imap_name="INBOX", anzeigename="Posteingang",
            uidvalidity=1, last_uid=0,
        )
        session.add(ordner)
        await session.flush()
        await session.refresh(account)
        await session.refresh(ordner)
        return account, ordner


async def _nachricht(
    account, ordner, *, uid: int, betreff: str, von_adresse: str = "kunde@example.de",
    message_id_header: str | None = None, gelesen: bool = False,
) -> MailMessage:
    async with system_session() as session:
        nachricht = MailMessage(
            mandant_id=account.mandant_id,
            mail_account_id=account.id,
            folder_id=ordner.id,
            uid=uid,
            von_name="Ein Kunde",
            von_adresse=von_adresse,
            an=[account.email_adresse],
            cc=[],
            betreff=betreff,
            body_text=f"Nachrichtentext {uid}",
            gelesen=gelesen,
            message_id_header=message_id_header or f"<{uid}@example.de>",
        )
        session.add(nachricht)
        await session.flush()
        await session.refresh(nachricht)
        return nachricht


@pytest.mark.asyncio
async def test_list_folders_nur_eigenes_konto(client, make_mandant, make_user):
    mandant = await make_mandant()
    user1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    user2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, _ = await _account_und_ordner(mandant, user1)
    token1 = await login(client, user1.email, "pw-123456")
    token2 = await login(client, user2.email, "pw-123456")

    resp1 = await client.get(f"/api/mail-accounts/{account.id}/folders", headers=auth_headers(token1))
    assert resp1.status_code == 200
    assert len(resp1.json()) == 1

    resp2 = await client.get(f"/api/mail-accounts/{account.id}/folders", headers=auth_headers(token2))
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_paginiert_und_zeigt_ausschnitt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    for i in range(3):
        await _nachricht(account, ordner, uid=i + 1, betreff=f"Betreff {i + 1}")
    token = await login(client, user.email, "pw-123456")

    resp = await client.get(f"/api/mail-folders/{ordner.id}/messages", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    # Neueste zuerst (created_at absteigend, da kein Date-Header gesetzt ist).
    assert body["items"][0]["betreff"] == "Betreff 3"
    assert "Nachrichtentext" in body["items"][0]["ausschnitt"]


@pytest.mark.asyncio
async def test_list_messages_volltextsuche(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    await _nachricht(account, ordner, uid=1, betreff="Angebot Heizungswartung")
    await _nachricht(account, ordner, uid=2, betreff="Rechnung Elektroinstallation")
    token = await login(client, user.email, "pw-123456")

    # "Rechnung" statt "Heizung" -- die deutsche Textsuchekonfiguration
    # zerlegt zusammengesetzte Woerter wie "Heizungswartung" nicht in
    # Teilwoerter, ein eigenstaendiges Wort im Betreff matcht aber sicher.
    resp = await client.get(
        f"/api/mail-folders/{ordner.id}/messages", headers=auth_headers(token), params={"suche": "Rechnung"}
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["betreff"] == "Rechnung Elektroinstallation"


@pytest.mark.asyncio
async def test_get_message_fremdes_konto_gibt_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    user1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    user2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user1)
    nachricht = await _nachricht(account, ordner, uid=1, betreff="Geheim")
    token2 = await login(client, user2.email, "pw-123456")

    resp = await client.get(f"/api/mail-messages/{nachricht.id}", headers=auth_headers(token2))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_message_setzt_gelesen(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    nachricht = await _nachricht(account, ordner, uid=1, betreff="Test", gelesen=False)
    token = await login(client, user.email, "pw-123456")

    resp = await client.patch(
        f"/api/mail-messages/{nachricht.id}", headers=auth_headers(token), json={"gelesen": True}
    )
    assert resp.status_code == 200
    assert resp.json()["gelesen"] is True

    async with system_session() as session:
        row = await session.get(MailMessage, nachricht.id)
        assert row.gelesen is True


@pytest.mark.asyncio
async def test_attachment_url_liefert_presigned_link(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    nachricht = await _nachricht(account, ordner, uid=1, betreff="Mit Anhang")
    async with system_session() as session:
        anhang = MailAttachment(
            mandant_id=mandant.id, message_id=nachricht.id, dateiname="beleg.pdf",
            mimetype="application/pdf", groesse_bytes=100, object_key="mail-nachrichten/test/beleg.pdf",
        )
        session.add(anhang)
        await session.flush()
        await session.refresh(anhang)
    token = await login(client, user.email, "pw-123456")

    resp = await client.get(
        f"/api/mail-messages/{nachricht.id}/attachments/{anhang.id}/url", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert "url" in resp.json()


@pytest.mark.asyncio
async def test_senden_ruft_mail_send_service_mit_richtigen_daten_auf(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, _ = await _account_und_ordner(mandant, user)
    token = await login(client, user.email, "pw-123456")

    aufrufe = []

    async def fake_sende(acc, **kwargs):
        aufrufe.append((acc.id, kwargs))

    monkeypatch.setattr("app.api.routes.mail_messages.sende_nachricht", fake_sende)

    resp = await client.post(
        f"/api/mail-accounts/{account.id}/senden",
        headers=auth_headers(token),
        json={"an": ["kunde@example.de"], "betreff": "Terminvorschlag", "text": "Wie besprochen."},
    )
    assert resp.status_code == 204
    assert len(aufrufe) == 1
    assert aufrufe[0][0] == account.id
    assert aufrufe[0][1]["an"] == ["kunde@example.de"]
    assert aufrufe[0][1]["betreff"] == "Terminvorschlag"


@pytest.mark.asyncio
async def test_senden_fremdes_konto_wird_abgelehnt(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    user2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, _ = await _account_und_ordner(mandant, user1)
    token2 = await login(client, user2.email, "pw-123456")

    monkeypatch.setattr("app.api.routes.mail_messages.sende_nachricht", lambda *a, **kw: None)

    resp = await client.post(
        f"/api/mail-accounts/{account.id}/senden",
        headers=auth_headers(token2),
        json={"an": ["kunde@example.de"], "betreff": "X", "text": "Y"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_antworten_setzt_re_praefix_und_threading_header(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    original = await _nachricht(
        account, ordner, uid=1, betreff="Anfrage Wartung", message_id_header="<original@kunde.de>",
    )
    token = await login(client, user.email, "pw-123456")

    aufrufe = []

    async def fake_sende(acc, **kwargs):
        aufrufe.append(kwargs)

    monkeypatch.setattr("app.api.routes.mail_messages.sende_nachricht", fake_sende)

    resp = await client.post(
        f"/api/mail-messages/{original.id}/antworten",
        headers=auth_headers(token),
        json={"an": ["kunde@example.de"], "text": "Gerne, wir kommen Dienstag."},
    )
    assert resp.status_code == 204
    assert aufrufe[0]["betreff"] == "Re: Anfrage Wartung"
    assert aufrufe[0]["in_reply_to"] == "<original@kunde.de>"
    assert aufrufe[0]["references"] == "<original@kunde.de>"


@pytest.mark.asyncio
async def test_antworten_verdoppelt_re_praefix_nicht(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    original = await _nachricht(account, ordner, uid=1, betreff="Re: Anfrage")
    token = await login(client, user.email, "pw-123456")

    aufrufe = []

    async def fake_sende(acc, **kwargs):
        aufrufe.append(kwargs)

    monkeypatch.setattr("app.api.routes.mail_messages.sende_nachricht", fake_sende)

    resp = await client.post(
        f"/api/mail-messages/{original.id}/antworten",
        headers=auth_headers(token),
        json={"an": ["kunde@example.de"], "text": "Ok."},
    )
    assert resp.status_code == 204
    assert aufrufe[0]["betreff"] == "Re: Anfrage"


@pytest.mark.asyncio
async def test_weiterleiten_zitiert_original(client, make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    account, ordner = await _account_und_ordner(mandant, user)
    original = await _nachricht(account, ordner, uid=1, betreff="Angebot", von_adresse="kunde@example.de")
    token = await login(client, user.email, "pw-123456")

    aufrufe = []

    async def fake_sende(acc, **kwargs):
        aufrufe.append(kwargs)

    monkeypatch.setattr("app.api.routes.mail_messages.sende_nachricht", fake_sende)

    resp = await client.post(
        f"/api/mail-messages/{original.id}/weiterleiten",
        headers=auth_headers(token),
        json={"an": ["kollege@example.de"], "text": "FYI"},
    )
    assert resp.status_code == 204
    assert aufrufe[0]["betreff"] == "Fwd: Angebot"
    assert "kunde@example.de" in aufrufe[0]["text"]
    assert "Nachrichtentext 1" in aufrufe[0]["text"]
