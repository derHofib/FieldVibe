"""Mail-Outbox: Versand nach dem Commit, Retry-Plan, kein Doppelversand, Mandantentrennung."""
import asyncio
import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.db.session import system_session, tenant_session
from app.models.email_log import EmailLog
from app.models.mail_outbox import MailOutbox
from app.models.notification import Notification
from app.services import email_service, mail_outbox_service, storage_service
from app.services.mail_outbox_service import (
    backoff_plan,
    enqueue_email,
    enqueue_email_and_log,
    naechster_versuch,
    verarbeite_outbox,
)
from tests.conftest import auth_headers, login

# In der Zukunft, damit die Zeilen (naechster_versuch_am = now()) zum simulierten Zeitpunkt faellig sind.
T0 = datetime(2099, 3, 10, 12, 0, tzinfo=timezone.utc)


class SmtpStub:
    """Ersetzt email_service.send_email: merkt sich Aufrufe, kann scheitern."""

    def __init__(self, fehler=None, dauer=0.0):
        self.aufrufe: list[dict] = []
        self.fehler = fehler
        self.dauer = dauer

    async def __call__(self, session, mandant_id, **kwargs):
        if self.dauer:
            await asyncio.sleep(self.dauer)
        self.aufrufe.append({"mandant_id": mandant_id, **kwargs})
        if self.fehler is not None:
            raise self.fehler


@pytest.fixture
def smtp(monkeypatch):
    stub = SmtpStub()
    monkeypatch.setattr(email_service, "send_email", stub)
    return stub


async def _einreihen(mandant, *, to="kunde@example.de", betreff="Betreff", log=True, **kwargs):
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        if log:
            eintrag = await enqueue_email_and_log(
                session, mandant.id, entity_type="kunde", entity_id=uuid.uuid4(), to=to, subject=betreff, body="Text", **kwargs
            )
            return eintrag
        return await enqueue_email(session, mandant.id, to=to, subject=betreff, body="Text", **kwargs)


async def _outbox(mandant=None) -> list[MailOutbox]:
    async with system_session() as session:
        stmt = select(MailOutbox).order_by(MailOutbox.created_at)
        if mandant is not None:
            stmt = stmt.where(MailOutbox.mandant_id == mandant.id)
        return list((await session.execute(stmt)).scalars().all())


async def _log(log_id) -> EmailLog:
    async with system_session() as session:
        return await session.get(EmailLog, log_id)


def test_backoff_plan_und_naechster_versuch():
    assert backoff_plan() == [1, 5, 30, 120, 720]
    assert naechster_versuch(1, T0) == T0 + timedelta(minutes=1)
    assert naechster_versuch(5, T0) == T0 + timedelta(hours=12)
    assert naechster_versuch(6, T0) is None


async def test_rollback_der_ausloesenden_transaktion_verschickt_keine_mail(make_mandant, smtp):
    mandant = await make_mandant()
    with pytest.raises(RuntimeError):
        async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
            await enqueue_email_and_log(
                session, mandant.id, entity_type="kunde", entity_id=uuid.uuid4(), to="x@example.de", subject="S", body="B"
            )
            raise RuntimeError("spaeterer Fehler im Request")

    assert await _outbox() == []
    async with system_session() as session:
        assert (await session.execute(select(EmailLog))).scalars().all() == []
    await verarbeite_outbox(jetzt=T0)
    assert smtp.aufrufe == []


async def test_versand_erst_nach_dem_commit_und_log_wird_nachgezogen(make_mandant, smtp):
    mandant = await make_mandant()
    log = await _einreihen(mandant)
    assert log.status == "ausstehend"
    assert smtp.aufrufe == [], "Einreihen darf nicht senden"

    ergebnis = await verarbeite_outbox(jetzt=T0)
    assert ergebnis["gesendet"] == 1
    assert smtp.aufrufe[0]["to"] == "kunde@example.de" and smtp.aufrufe[0]["mandant_id"] == mandant.id
    [zeile] = await _outbox(mandant)
    assert zeile.status == "sent" and zeile.versuche == 1 and zeile.gesendet_am == T0
    assert (await _log(log.id)).status == "gesendet"

    await verarbeite_outbox(jetzt=T0 + timedelta(hours=1))
    assert len(smtp.aufrufe) == 1, "gesendete Mail wird nie erneut verschickt"


async def test_retry_plan_mit_exponentiellem_backoff_dann_failed_und_benachrichtigung(
    make_mandant, make_user, smtp, caplog
):
    mandant = await make_mandant()
    ersteller = await make_user(mandant=mandant, role="mandant_admin")
    smtp.fehler = TimeoutError("SMTP nicht erreichbar")
    log = await _einreihen(mandant, gesendet_von=ersteller.id)
    caplog.set_level(logging.WARNING, logger="app.mail_outbox")

    await verarbeite_outbox(jetzt=T0)
    assert len(smtp.aufrufe) == 1
    t = T0
    for versuch, warte in enumerate((1, 5, 30, 120, 720), start=2):
        kurz_davor = t + timedelta(minutes=warte) - timedelta(seconds=1)
        await verarbeite_outbox(jetzt=kurz_davor)
        assert len(smtp.aufrufe) == versuch - 1, f"vor Ablauf von {warte} min darf nichts gesendet werden"
        t += timedelta(minutes=warte)
        await verarbeite_outbox(jetzt=t)
        assert len(smtp.aufrufe) == versuch, f"nach {warte} min muss Versuch {versuch} laufen"

    [zeile] = await _outbox(mandant)
    assert len(smtp.aufrufe) == 6 and zeile.versuche == 6
    assert zeile.status == "failed" and "SMTP nicht erreichbar" in zeile.letzter_fehler
    eintrag = await _log(log.id)
    assert eintrag.status == "fehler" and "SMTP nicht erreichbar" in eintrag.fehlermeldung
    async with system_session() as session:
        meldungen = (await session.execute(select(Notification).where(Notification.user_id == ersteller.id))).scalars().all()
    assert len(meldungen) == 1 and "nicht zugestellt" in meldungen[0].titel
    assert any(getattr(r, "event", "") == "mail_outbox_failed" for r in caplog.records)

    await verarbeite_outbox(jetzt=t + timedelta(days=2))
    assert len(smtp.aufrufe) == 6, "failed wird nicht von selbst wiederholt"


async def test_zwischenstand_zeigt_naechsten_versuch_im_verlauf(make_mandant, smtp):
    mandant = await make_mandant()
    smtp.fehler = TimeoutError("zu langsam")
    log = await _einreihen(mandant)
    await verarbeite_outbox(jetzt=T0)
    eintrag = await _log(log.id)
    assert eintrag.status == "ausstehend"
    assert "Versuch 1 fehlgeschlagen" in eintrag.fehlermeldung and "nächster Versuch" in eintrag.fehlermeldung


async def test_erfolg_nach_fehlversuch_setzt_log_zurueck_und_loescht_anhaenge(make_mandant, smtp):
    mandant = await make_mandant()
    smtp.fehler = TimeoutError("kurz weg")
    log = await _einreihen(mandant, attachment=("a.pdf", b"%PDF-1", "application/pdf"))
    [zeile] = await _outbox(mandant)
    key = zeile.anhaenge[0]["s3_key"]
    await verarbeite_outbox(jetzt=T0)

    smtp.fehler = None
    await verarbeite_outbox(jetzt=T0 + timedelta(minutes=2))
    [zeile] = await _outbox(mandant)
    assert zeile.status == "sent" and zeile.versuche == 2 and zeile.letzter_fehler is None
    eintrag = await _log(log.id)
    assert eintrag.status == "gesendet" and eintrag.fehlermeldung is None
    with pytest.raises(ClientError):
        storage_service._internal_client.head_object(Bucket=storage_service.BUCKET, Key=key)


@pytest.mark.parametrize(
    "fehler",
    [
        email_service.EmailNichtKonfiguriert(),
        smtplib.SMTPRecipientsRefused({"x@example.de": (550, b"unbekannt")}),
        smtplib.SMTPDataError(554, b"abgelehnt"),
    ],
)
async def test_dauerhafte_fehler_werden_nicht_wiederholt(make_mandant, smtp, fehler):
    mandant = await make_mandant()
    smtp.fehler = fehler
    log = await _einreihen(mandant)
    await verarbeite_outbox(jetzt=T0)
    await verarbeite_outbox(jetzt=T0 + timedelta(days=1))
    assert len(smtp.aufrufe) == 1
    [zeile] = await _outbox(mandant)
    assert zeile.status == "failed"
    assert (await _log(log.id)).status == "fehler"


async def test_ohne_smtp_konfiguration_klare_meldung(make_mandant):
    mandant = await make_mandant()
    log = await _einreihen(mandant)
    await verarbeite_outbox(jetzt=T0)
    eintrag = await _log(log.id)
    assert eintrag.status == "fehler" and "Kein SMTP-Postfach" in eintrag.fehlermeldung


async def test_anhaenge_kommen_vollstaendig_und_in_reihenfolge_an(make_mandant, smtp):
    mandant = await make_mandant()
    await _einreihen(
        mandant,
        attachment=("rechnung.pdf", b"%PDF-1.7 inhalt", "application/pdf"),
        weitere_anhaenge=[("x.xml", b"<xml/>", "application/xml"), ("c.csv", b"a;b", "text/csv")],
    )
    [zeile] = await _outbox(mandant)
    assert [a["dateiname"] for a in zeile.anhaenge] == ["rechnung.pdf", "x.xml", "c.csv"]
    for a in zeile.anhaenge:
        assert mandant.id.hex[:0] == "" and str(mandant.id) in a["s3_key"]

    await verarbeite_outbox(jetzt=T0)
    aufruf = smtp.aufrufe[0]
    assert aufruf["attachment"] == ("rechnung.pdf", b"%PDF-1.7 inhalt", "application/pdf")
    assert aufruf["weitere_anhaenge"] == [("x.xml", b"<xml/>", "application/xml"), ("c.csv", b"a;b", "text/csv")]


async def test_zwei_worker_parallel_senden_jede_mail_genau_einmal(make_mandant, smtp):
    mandant = await make_mandant()
    smtp.dauer = 0.15
    for i in range(8):
        await _einreihen(mandant, to=f"empfaenger{i}@example.de")

    a, b, c = await asyncio.gather(
        verarbeite_outbox(max_anzahl=3, jetzt=T0), verarbeite_outbox(max_anzahl=3, jetzt=T0), verarbeite_outbox(max_anzahl=3, jetzt=T0)
    )
    await verarbeite_outbox(max_anzahl=10, jetzt=T0)
    empfaenger = [x["to"] for x in smtp.aufrufe]
    assert sorted(empfaenger) == sorted(f"empfaenger{i}@example.de" for i in range(8))
    assert len(set(empfaenger)) == 8, "kein Doppelversand"
    assert a["gesendet"] + b["gesendet"] + c["gesendet"] >= 6


async def test_abgestuerzter_worker_fuehrt_nicht_zum_doppelversand(make_mandant, make_user, smtp):
    mandant = await make_mandant()
    ersteller = await make_user(mandant=mandant, role="mandant_admin")
    log = await _einreihen(mandant, gesendet_von=ersteller.id)
    # Worker-Crash nach dem SMTP-Erfolg, vor dem Rueckschreiben.
    original = mail_outbox_service._schreibe_ergebnis

    async def stirbt(*args, **kwargs):
        raise ConnectionError("DB weg")

    mail_outbox_service._schreibe_ergebnis = stirbt
    try:
        await verarbeite_outbox(jetzt=T0)
    finally:
        mail_outbox_service._schreibe_ergebnis = original
    assert len(smtp.aufrufe) == 1
    [zeile] = await _outbox(mandant)
    assert zeile.status == "sending"

    # Noch nicht ueberfaellig: unveraendert, kein erneuter Versand.
    await verarbeite_outbox(jetzt=T0 + timedelta(minutes=5))
    assert (await _outbox(mandant))[0].status == "sending"

    ergebnis = await verarbeite_outbox(jetzt=T0 + timedelta(minutes=20))
    assert ergebnis["abgebrochen_unklar"] == 1
    assert len(smtp.aufrufe) == 1, "NICHT erneut gesendet"
    assert (await _outbox(mandant))[0].status == "failed"
    eintrag = await _log(log.id)
    assert eintrag.status == "fehler" and "Zustellung unbekannt" in eintrag.fehlermeldung
    async with system_session() as session:
        assert (await session.execute(select(Notification).where(Notification.user_id == ersteller.id))).scalars().all()


async def test_mandantentrennung_rls_und_api(client, make_mandant, make_user, smtp):
    a = await make_mandant("Alpha")
    b = await make_mandant("Beta")
    admin_a = await make_user(mandant=a, role="mandant_admin", email="a@example.de", password="pw-123456")
    admin_b = await make_user(mandant=b, role="mandant_admin", email="b@example.de", password="pw-123456")
    smtp.fehler = smtplib.SMTPDataError(554, b"nein")
    await _einreihen(a, to="an-a@example.de")
    await _einreihen(b, to="an-b@example.de")
    await verarbeite_outbox(jetzt=T0)

    async with tenant_session(mandant_id=a.id, is_super_admin=False) as session:
        zeilen = (await session.execute(select(MailOutbox))).scalars().all()
    assert [z.empfaenger for z in zeilen] == ["an-a@example.de"]

    token_a = await login(client, "a@example.de", "pw-123456")
    liste = (await client.get("/api/mail-outbox", headers=auth_headers(token_a))).json()
    assert [z["empfaenger"] for z in liste] == ["an-a@example.de"]
    assert "body" not in liste[0]

    fremde = (await _outbox(b))[0]
    resp = await client.post(f"/api/mail-outbox/{fremde.id}/wiederholen", headers=auth_headers(token_a))
    assert resp.status_code == 404
    assert (await _outbox(b))[0].status == "failed"

    super_admin = await make_user(mandant=None, role="super_admin", email="sa@example.de", password="pw-123456")
    token_sa = await login(client, "sa@example.de", "pw-123456")
    alle = (await client.get("/api/mail-outbox", headers=auth_headers(token_sa))).json()
    assert {z["empfaenger"] for z in alle} == {"an-a@example.de", "an-b@example.de"}


async def test_api_wiederholen_stoesst_neuen_versand_an(client, make_mandant, make_user, smtp):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin", email="a@example.de", password="pw-123456")
    smtp.fehler = smtplib.SMTPDataError(554, b"nein")
    log = await _einreihen(mandant)
    await verarbeite_outbox(jetzt=T0)
    token = await login(client, "a@example.de", "pw-123456")
    [fehlgeschlagen] = (await client.get("/api/mail-outbox", headers=auth_headers(token))).json()

    smtp.fehler = None
    resp = await client.post(f"/api/mail-outbox/{fehlgeschlagen['id']}/wiederholen", headers=auth_headers(token))
    assert resp.status_code == 200 and resp.json()["status"] == "pending" and resp.json()["versuche"] == 0
    assert (await _log(log.id)).status == "ausstehend"
    await verarbeite_outbox(jetzt=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert (await _outbox(mandant))[0].status == "sent"
    assert (await _log(log.id)).status == "gesendet"
    # Gesendete Mail laesst sich nicht erneut anstossen.
    assert (await client.post(f"/api/mail-outbox/{fehlgeschlagen['id']}/wiederholen", headers=auth_headers(token))).status_code == 404


async def test_api_nur_fuer_administratoren(client, make_mandant, make_user):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="techniker", email="t@example.de", password="pw-123456")
    token = await login(client, "t@example.de", "pw-123456")
    assert (await client.get("/api/mail-outbox", headers=auth_headers(token))).status_code == 403
    assert (await client.get("/api/mail-outbox")).status_code in (401, 403)
