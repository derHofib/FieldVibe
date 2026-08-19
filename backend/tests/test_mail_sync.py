from email.message import EmailMessage

import pytest
from sqlalchemy import select

from app.core.security import encrypt_secret
from app.db.session import system_session
from app.models.mail_account import MailAccount
from app.models.mail_attachment import MailAttachment
from app.models.mail_folder import MailFolder
from app.models.mail_message import MailMessage
from app.services import mail_sync_service, storage_service
from app.services.mail_sync_service import OrdnerSyncErgebnis, RohNachricht


def _rfc822(
    *, absender: str, betreff: str, an: str = "technik@example.de", text: str = "Hallo, siehe Anhang.",
    mit_pdf_anhang: bool = False, message_id: str | None = None,
) -> bytes:
    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = an
    nachricht["Subject"] = betreff
    if message_id:
        nachricht["Message-ID"] = message_id
    nachricht.set_content(text)
    if mit_pdf_anhang:
        nachricht.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="beleg.pdf")
    return bytes(nachricht)


async def _make_account(make_mandant, make_user) -> MailAccount:
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker")
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
        )
        session.add(account)
        await session.flush()
        await session.refresh(account)
        return account


@pytest.mark.asyncio
async def test_sync_account_legt_ordner_und_nachricht_mit_anhang_an(make_mandant, make_user, monkeypatch):
    account = await _make_account(make_mandant, make_user)

    rohdaten = _rfc822(
        absender="Sonepar <buchhaltung@sonepar.de>", betreff="Angebot", mit_pdf_anhang=True,
        message_id="<abc@sonepar.de>",
    )

    def fake_sync(account_obj, passwort, bekannte_ordner):
        assert passwort == "geheim"
        assert bekannte_ordner == {}
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX",
                anzeigename="Posteingang",
                delimiter="/",
                uidvalidity=111,
                zuruckgesetzt=False,
                neue_uid_grenze=5,
                nachrichten=[RohNachricht(uid=5, rohdaten=rohdaten, gelesen=False)],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync)

    async with system_session() as session:
        acc = await session.get(MailAccount, account.id)
        ergebnis = await mail_sync_service.sync_account(session, acc)
        assert ergebnis == {"ordner": 1, "neue_nachrichten": 1}

    async with system_session() as session:
        ordner = (
            (await session.execute(select(MailFolder).where(MailFolder.mail_account_id == account.id)))
            .scalars().all()
        )
        assert len(ordner) == 1
        assert ordner[0].imap_name == "INBOX"
        assert ordner[0].uidvalidity == 111
        assert ordner[0].last_uid == 5

        nachrichten = (
            (await session.execute(select(MailMessage).where(MailMessage.mail_account_id == account.id)))
            .scalars().all()
        )
        assert len(nachrichten) == 1
        nachricht = nachrichten[0]
        assert nachricht.uid == 5
        assert nachricht.von_adresse == "buchhaltung@sonepar.de"
        assert nachricht.betreff == "Angebot"
        assert nachricht.gelesen is False
        assert nachricht.message_id_header == "<abc@sonepar.de>"

        anhaenge = (
            (await session.execute(select(MailAttachment).where(MailAttachment.message_id == nachricht.id)))
            .scalars().all()
        )
        assert len(anhaenge) == 1
        assert anhaenge[0].dateiname == "beleg.pdf"
        inhalt = await storage_service.download_bytes(anhaenge[0].object_key)
        assert inhalt.startswith(b"%PDF-1.4")


@pytest.mark.asyncio
async def test_sync_account_zweiter_lauf_ohne_neue_uids_bleibt_unveraendert(make_mandant, make_user, monkeypatch):
    account = await _make_account(make_mandant, make_user)

    def fake_sync_erster_lauf(account_obj, passwort, bekannte_ordner):
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX", anzeigename="Posteingang", delimiter="/", uidvalidity=1,
                zuruckgesetzt=False, neue_uid_grenze=3,
                nachrichten=[RohNachricht(uid=3, rohdaten=_rfc822(absender="a@b.de", betreff="Eins"), gelesen=True)],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync_erster_lauf)
    async with system_session() as session:
        acc = await session.get(MailAccount, account.id)
        await mail_sync_service.sync_account(session, acc)

    def fake_sync_zweiter_lauf(account_obj, passwort, bekannte_ordner):
        assert bekannte_ordner == {"INBOX": (1, 3)}
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX", anzeigename="Posteingang", delimiter="/", uidvalidity=1,
                zuruckgesetzt=False, neue_uid_grenze=3, nachrichten=[],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync_zweiter_lauf)
    async with system_session() as session:
        acc = await session.get(MailAccount, account.id)
        ergebnis = await mail_sync_service.sync_account(session, acc)
        assert ergebnis == {"ordner": 1, "neue_nachrichten": 0}

    async with system_session() as session:
        nachrichten = (
            (await session.execute(select(MailMessage).where(MailMessage.mail_account_id == account.id)))
            .scalars().all()
        )
        assert len(nachrichten) == 1


@pytest.mark.asyncio
async def test_sync_account_uidvalidity_wechsel_baut_ordner_neu_auf(make_mandant, make_user, monkeypatch):
    account = await _make_account(make_mandant, make_user)

    def fake_sync_erster_lauf(account_obj, passwort, bekannte_ordner):
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX", anzeigename="Posteingang", delimiter="/", uidvalidity=1,
                zuruckgesetzt=False, neue_uid_grenze=9,
                nachrichten=[RohNachricht(uid=9, rohdaten=_rfc822(absender="a@b.de", betreff="Alt"), gelesen=True)],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync_erster_lauf)
    async with system_session() as session:
        acc = await session.get(MailAccount, account.id)
        await mail_sync_service.sync_account(session, acc)

    def fake_sync_nach_uidvalidity_wechsel(account_obj, passwort, bekannte_ordner):
        assert bekannte_ordner == {"INBOX": (1, 9)}
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX", anzeigename="Posteingang", delimiter="/", uidvalidity=2,
                zuruckgesetzt=True, neue_uid_grenze=1,
                nachrichten=[RohNachricht(uid=1, rohdaten=_rfc822(absender="c@d.de", betreff="Neu"), gelesen=False)],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync_nach_uidvalidity_wechsel)
    async with system_session() as session:
        acc = await session.get(MailAccount, account.id)
        await mail_sync_service.sync_account(session, acc)

    async with system_session() as session:
        ordner = (
            (await session.execute(select(MailFolder).where(MailFolder.mail_account_id == account.id)))
            .scalars().all()
        )
        assert len(ordner) == 1
        assert ordner[0].uidvalidity == 2
        assert ordner[0].last_uid == 1

        nachrichten = (
            (await session.execute(select(MailMessage).where(MailMessage.mail_account_id == account.id)))
            .scalars().all()
        )
        assert len(nachrichten) == 1
        assert nachrichten[0].betreff == "Neu"


@pytest.mark.asyncio
async def test_run_mail_sync_ein_fehlerhaftes_konto_stoppt_nicht_die_anderen(make_mandant, make_user, monkeypatch):
    konto_ok = await _make_account(make_mandant, make_user)
    mandant2 = await make_mandant(name="Betrieb2")
    user2 = await make_user(mandant=mandant2, role="techniker")
    async with system_session() as session:
        konto_kaputt = MailAccount(
            mandant_id=mandant2.id,
            user_id=user2.id,
            name="Kaputtes Postfach",
            email_adresse="kaputt@example.de",
            imap_host="imap.kaputt.de",
            imap_port=993,
            imap_verschluesselung="ssl",
            imap_benutzername="kaputt@example.de",
            smtp_host="smtp.kaputt.de",
            smtp_port=587,
            smtp_verschluesselung="starttls",
            smtp_benutzername="kaputt@example.de",
            passwort_verschluesselt=encrypt_secret("geheim"),
        )
        session.add(konto_kaputt)
        await session.flush()
        await session.refresh(konto_kaputt)

    def fake_sync(account_obj, passwort, bekannte_ordner):
        if account_obj.id == konto_kaputt.id:
            raise TimeoutError("Verbindung zu imap.kaputt.de fehlgeschlagen")
        return [
            OrdnerSyncErgebnis(
                imap_name="INBOX", anzeigename="Posteingang", delimiter="/", uidvalidity=1,
                zuruckgesetzt=False, neue_uid_grenze=1,
                nachrichten=[RohNachricht(uid=1, rohdaten=_rfc822(absender="a@b.de", betreff="Ok"), gelesen=False)],
            )
        ]

    monkeypatch.setattr(mail_sync_service, "_sync_account_blockierend", fake_sync)

    ergebnis = await mail_sync_service.run_mail_sync([konto_ok.id, konto_kaputt.id])
    assert ergebnis == {"konten_synchronisiert": 1, "fehler": 1}

    async with system_session() as session:
        kaputt = await session.get(MailAccount, konto_kaputt.id)
        assert kaputt.letzter_sync_fehler is not None

        ok = await session.get(MailAccount, konto_ok.id)
        assert ok.letzter_sync_fehler is None
        assert ok.letzter_sync_am is not None


def test_parse_list_zeile_mit_anfuehrungszeichen():
    ergebnis = mail_sync_service._parse_list_zeile(b'(\\HasNoChildren) "/" "INBOX"')
    assert ergebnis == (["\\HasNoChildren"], "/", "INBOX")


def test_parse_list_zeile_ohne_anfuehrungszeichen():
    ergebnis = mail_sync_service._parse_list_zeile(b'(\\HasNoChildren \\Sent) "/" Sent')
    assert ergebnis == (["\\HasNoChildren", "\\Sent"], "/", "Sent")


def test_parse_list_zeile_unbekanntes_format_gibt_none():
    assert mail_sync_service._parse_list_zeile(b"kompletter Unsinn") is None


def test_anzeigename_inbox_wird_uebersetzt():
    assert mail_sync_service._anzeigename("INBOX", "/") == "Posteingang"


def test_anzeigename_verschachtelter_ordner_nimmt_letztes_segment():
    assert mail_sync_service._anzeigename("INBOX/Archiv/2024", "/") == "2024"


def test_parse_fetch_flags_erkennt_seen():
    assert mail_sync_service._parse_fetch_flags(rb"1 (FLAGS (\Seen) RFC822 {123}") is True
    assert mail_sync_service._parse_fetch_flags(rb"1 (FLAGS () RFC822 {123}") is False
