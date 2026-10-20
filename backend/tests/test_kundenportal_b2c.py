"""Kundenportal B2C (Migration 0111): Annahmenachweis, Button-Loesung,
Widerrufsbutton, append-only/RLS, Einstellungen und Barrierefreiheits-Angaben.

Alle Rechtstexte sind Platzhalter; getestet wird der technische Ablauf."""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.db.session import system_session, tenant_session
from app.main import app
from app.models.angebot import Angebot, AngebotPosition
from app.models.angebot_annahme import AngebotAnnahme
from app.models.email_log import EmailLog
from app.models.mandant import Mandant
from app.models.notification import Notification
from app.models.rechnung import Rechnung
from app.models.vorgang_event import VorgangEvent
from app.services import verbraucherschutz_service as vs
from app.services.angebot_service import berechne_fassung_sha256
from tests.conftest import auth_headers, login
from tests.test_kundenportal import _kunden_login, _make_zugang
from tests.test_steuer_je_position import _migrieren, _spalten, _sync_engine

POSITIONEN = [
    {"beschreibung": "Heizkörper tauschen", "menge": "2", "einheit": "Stk", "einzelpreis": "100.00"},
    {"beschreibung": "Montage", "menge": "3", "einheit": "Std", "einzelpreis": "50.00", "positionstyp": "arbeitszeit"},
]
B2C = {"portal_verbraucherschutz": "nur_privatkunden"}


@pytest.fixture
def mails(monkeypatch):
    """Faengt den Mailversand ab (send_email_and_log schreibt trotzdem den
    EmailLog); jeder Eintrag sind die Schluesselwoerter des send_email-Aufrufs."""
    gesendet: list[dict] = []

    async def _fake(session, mandant_id, **kwargs):
        gesendet.append(kwargs)

    monkeypatch.setattr("app.services.email_service.send_email", _fake)
    return gesendet


async def _firmendaten(mandant, **werte) -> None:
    async with system_session() as session:
        m = await session.get(Mandant, mandant.id)
        m.firmendaten = {**(m.firmendaten or {}), **werte}


async def _aufbau(
    client,
    make_mandant,
    make_user,
    make_kunde,
    *,
    kunde_typ="privat",
    firmendaten=B2C,
    email="portal@example.de",
    versenden=True,
):
    mandant = await make_mandant()
    if firmendaten:
        await _firmendaten(mandant, **firmendaten)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Familie Beispiel", typ=kunde_typ)
    zugang = await _make_zugang(mandant, kunde, email=email, name="Erika Beispiel")
    admin_h = auth_headers(await login(client, admin.email, "pw-123456"))
    erstellt = await client.post(
        "/api/angebote", headers=admin_h, json={"kunde_id": str(kunde.id), "positionen": POSITIONEN}
    )
    assert erstellt.status_code == 201, erstellt.text
    angebot_id = erstellt.json()["id"]
    if versenden:
        r = await client.patch(f"/api/angebote/{angebot_id}", headers=admin_h, json={"status": "versendet"})
        assert r.status_code == 200, r.text
    tokens = await _kunden_login(client, email, "kunden-pw-123")
    return {
        "mandant": mandant,
        "admin": admin,
        "kunde": kunde,
        "zugang": zugang,
        "admin_h": admin_h,
        "h": auth_headers(tokens["access_token"]),
        "angebot_id": angebot_id,
    }


async def _belehrung(client, h) -> dict:
    r = await client.get("/api/kundenportal/verbraucherschutz", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _b2c_body(belehrung_version: str, **extra) -> dict:
    return {"status": "angenommen", "bestaetigung": True, "belehrung_version": belehrung_version, **extra}


async def _nachweise(angebot_id) -> list[AngebotAnnahme]:
    async with system_session() as session:
        result = await session.execute(
            select(AngebotAnnahme)
            .where(AngebotAnnahme.angebot_id == uuid.UUID(str(angebot_id)))
            .order_by(AngebotAnnahme.created_at, AngebotAnnahme.id)
        )
        return list(result.scalars().all())


async def _b2c_annehmen(client, ctx, **headers) -> dict:
    version = (await _belehrung(client, ctx["h"]))["belehrung"]["version"]
    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers={**ctx["h"], **headers},
        json=_b2c_body(version),
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- Annahmenachweis (immer, auch B2B) ------------------------------------------------------


async def test_b2b_annahme_ohne_pflichtfelder_wie_bisher_mit_nachweis(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers={**ctx["h"], "User-Agent": "Testbrowser/1.0"},
        json={"status": "angenommen"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "angenommen"
    assert r.json()["verbraucherschutz"] is False
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.aktion == "annahme"
    assert nachweis.kunden_portal_zugang_id == ctx["zugang"].id
    assert nachweis.zugang_email == "portal@example.de"
    assert nachweis.zugang_name == "Erika Beispiel"
    assert nachweis.ip == "127.0.0.1"
    assert nachweis.user_agent == "Testbrowser/1.0"
    assert nachweis.mandant_id == ctx["mandant"].id
    assert nachweis.b2c_flag is False
    assert nachweis.belehrung_version is None and nachweis.belehrung_text is None
    assert len(nachweis.fassung_sha256) == 64
    assert mails == []  # Bestaetigungsmail gibt es nur im B2C-Ablauf


async def test_ablehnung_wird_protokolliert_auch_bei_verbraucher_ohne_belehrung(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "abgelehnt"}
    )

    assert r.status_code == 200, r.text
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.aktion == "ablehnung"
    assert nachweis.b2c_flag is True  # Verbraucher-Ablauf war aktiv, nur eben ohne Pflichtfelder
    assert nachweis.belehrung_version is None
    assert mails == []


async def test_user_agent_wird_auf_300_zeichen_gekuerzt(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")

    await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers={**ctx["h"], "User-Agent": "A" * 450},
        json={"status": "angenommen"},
    )

    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.user_agent == "A" * 300


async def test_ip_kommt_wie_beim_login_limiter_aus_dem_vertrauenswuerdigen_proxy(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
    async with AsyncClient(
        transport=ASGITransport(app=wrapped, client=("172.18.0.5", 40000)), base_url="http://test"
    ) as ac:
        r = await ac.patch(
            f"/api/kundenportal/angebote/{ctx['angebot_id']}",
            headers={**ctx["h"], "X-Forwarded-For": "203.0.113.9"},
            json={"status": "angenommen"},
        )
    assert r.status_code == 200, r.text
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.ip == "203.0.113.9"


async def test_gefaelschter_forwarded_for_header_wird_ignoriert(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12")
    async with AsyncClient(
        transport=ASGITransport(app=wrapped, client=("198.51.100.7", 5555)), base_url="http://test"
    ) as ac:
        r = await ac.patch(
            f"/api/kundenportal/angebote/{ctx['angebot_id']}",
            headers={**ctx["h"], "X-Forwarded-For": "10.0.0.99"},
            json={"status": "angenommen"},
        )
    assert r.status_code == 200, r.text
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.ip == "198.51.100.7"


async def test_office_angebot_zeigt_letzten_nachweis(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    vorher = (await client.get(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"])).json()
    assert vorher["letzter_nachweis"] is None and len(vorher["fassung_sha256"]) == 64

    await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "angenommen"}
    )

    angebot = (await client.get(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"])).json()
    nachweis = angebot["letzter_nachweis"]
    assert nachweis["aktion"] == "annahme"
    assert nachweis["zugang_email"] == "portal@example.de"
    assert nachweis["ip"] == "127.0.0.1"
    assert nachweis["fassung_sha256"] == vorher["fassung_sha256"] == angebot["fassung_sha256"]


async def test_portal_antworten_enthalten_keine_nachweis_interna(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    angenommen = await _b2c_annehmen(client, ctx)
    liste = await client.get("/api/kundenportal/angebote", headers=ctx["h"])
    for body in (angenommen, liste.json()[0]):
        assert {"ip", "user_agent", "zugang_email", "letzter_nachweis", "belehrung_text"}.isdisjoint(body)
        assert body["nachweis_referenz"]


# --- Fassungs-Hash ---------------------------------------------------------------------------


def _angebot_objekte(**abweichung):
    angebot = Angebot(
        id=uuid.uuid4(),
        mandant_id=uuid.UUID(int=1),
        kunde_id=uuid.UUID(int=2),
        angebotsnummer="A-1",
        mwst_satz=Decimal("19.00"),
        gueltig_bis=date(2026, 12, 31),
    )
    positionen = [
        AngebotPosition(
            id=uuid.uuid4(), position=1, beschreibung="Heizkörper", menge=Decimal("2.00"),
            einheit="Stk", einzelpreis=Decimal("100.00"), artikelnummer="ART-1", positionstyp="material",
        ),
        AngebotPosition(
            id=uuid.uuid4(), position=2, beschreibung="Montage", menge=Decimal("3.00"),
            einheit="Std", einzelpreis=Decimal("50.00"), positionstyp="arbeitszeit",
        ),
    ]
    return angebot, positionen


def test_fassungs_hash_ist_stabil_und_unabhaengig_von_ids_reihenfolge_und_zahlenformat():
    angebot, positionen = _angebot_objekte()
    basis = berechne_fassung_sha256(angebot, positionen)
    assert basis == berechne_fassung_sha256(angebot, positionen)

    andere_ids, andere_positionen = _angebot_objekte()
    andere_ids.id = uuid.uuid4()
    andere_positionen[0].artikelnummer = "ANDERS"  # nicht kundensichtbar
    andere_positionen[0].positionstyp = "arbeitszeit"
    andere_positionen[0].menge = Decimal("2")  # 2 statt 2.00
    andere_positionen[1].einzelpreis = Decimal("50")
    assert berechne_fassung_sha256(andere_ids, list(reversed(andere_positionen))) == basis


@pytest.mark.parametrize(
    "aenderung",
    [
        lambda a, p: setattr(p[0], "einzelpreis", Decimal("100.01")),
        lambda a, p: setattr(p[0], "menge", Decimal("3")),
        lambda a, p: setattr(p[0], "beschreibung", "Heizkörper tauschen"),
        lambda a, p: setattr(p[1], "einheit", "h"),
        lambda a, p: setattr(a, "gueltig_bis", date(2027, 1, 1)),
        lambda a, p: setattr(a, "gueltig_bis", None),
        lambda a, p: setattr(a, "mwst_satz", Decimal("7.00")),
        lambda a, p: setattr(a, "angebotsnummer", "A-2"),
        lambda a, p: p.pop(),
        lambda a, p: setattr(p[0], "position", 3),
    ],
)
def test_fassungs_hash_aendert_sich_bei_jeder_inhaltlichen_aenderung(aenderung):
    angebot, positionen = _angebot_objekte()
    basis = berechne_fassung_sha256(angebot, positionen)
    aenderung(angebot, positionen)
    assert berechne_fassung_sha256(angebot, positionen) != basis


def test_pdf_ist_als_hashgrundlage_ungeeignet_weil_nicht_deterministisch():
    # Begruendung der kanonischen Serialisierung: dieselben Daten ergeben als PDF
    # bei jedem Abruf andere Bytes (Erstellzeit/Dokument-ID in den Metadaten).
    import hashlib
    import time

    from app.models.kunde import Kunde
    from app.services.pdf_service import generate_angebot_pdf

    angebot, positionen = _angebot_objekte()
    angebot.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mandant = Mandant(id=uuid.uuid4(), name="Test", slug="t", firmendaten={})
    kunde = Kunde(id=uuid.uuid4(), kundennummer="K1", name="Kunde", adresse={})
    erstes = hashlib.sha256(generate_angebot_pdf(mandant, angebot, positionen, kunde)).hexdigest()
    time.sleep(1.2)
    zweites = hashlib.sha256(generate_angebot_pdf(mandant, angebot, positionen, kunde)).hexdigest()
    assert erstes != zweites


async def test_hash_ueber_api_gleich_im_portal_und_nachweis(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    portal = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    erneut = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert portal["fassung_sha256"] == erneut["fassung_sha256"]

    await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "angenommen"}
    )
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.fassung_sha256 == portal["fassung_sha256"]


async def test_fassung_aus_dem_client_muss_passen_sonst_409_und_nichts_geaendert(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    gesehen = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    # Betrieb verlaengert die Gueltigkeit, nachdem der Kunde die Seite geladen hat.
    await client.patch(
        f"/api/angebote/{ctx['angebot_id']}",
        headers=ctx["admin_h"],
        json={"gueltig_bis": str(date.today() + timedelta(days=90))},
    )

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers=ctx["h"],
        json={"status": "angenommen", "fassung_sha256": gesehen["fassung_sha256"]},
    )
    assert r.status_code == 409
    assert await _nachweise(ctx["angebot_id"]) == []
    angebot = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert angebot["status"] == "versendet"

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers=ctx["h"],
        json={"status": "angenommen", "fassung_sha256": angebot["fassung_sha256"]},
    )
    assert r.status_code == 200, r.text


# --- B2B/B2C-Schalter -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kunde_typ, firmendaten",
    [
        ("privat", {}),  # Bestandsmandant: Schluessel fehlt -> "aus"
        ("privat", {"portal_verbraucherschutz": "aus"}),
        ("gewerbe", B2C),
        ("hausverwaltung", B2C),
        ("oeffentlich", B2C),
        (None, B2C),
    ],
)
async def test_ohne_aktiven_schutz_oder_verbraucher_gilt_der_alte_ablauf(
    client, make_mandant, make_user, make_kunde, mails, kunde_typ, firmendaten
):
    ctx = await _aufbau(
        client, make_mandant, make_user, make_kunde, kunde_typ=kunde_typ, firmendaten=firmendaten
    )
    assert (await _belehrung(client, ctx["h"]))["verbraucherschutz"] is False

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "angenommen"}
    )

    assert r.status_code == 200, r.text
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.b2c_flag is False
    assert mails == []


async def test_b2c_annahme_braucht_bestaetigung_und_aktuelle_belehrung(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    url = f"/api/kundenportal/angebote/{ctx['angebot_id']}"
    version = (await _belehrung(client, ctx["h"]))["belehrung"]["version"]

    for body in (
        {"status": "angenommen"},
        {"status": "angenommen", "bestaetigung": False, "belehrung_version": version},
        {"status": "angenommen", "bestaetigung": True},
        {"status": "angenommen", "bestaetigung": True, "belehrung_version": "veraltet"},
    ):
        r = await client.patch(url, headers=ctx["h"], json=body)
        assert r.status_code == 422, (body, r.text)

    assert await _nachweise(ctx["angebot_id"]) == []
    assert (await client.get(url, headers=ctx["h"])).json()["status"] == "versendet"
    assert mails == []


async def test_verbraucherschutz_endpunkt_liefert_platzhalter_gekennzeichnet(
    client, make_mandant, make_user, make_kunde
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)

    daten = await _belehrung(client, ctx["h"])

    assert daten["verbraucherschutz"] is True
    assert daten["widerrufsfrist_tage"] == 14 == vs.WIDERRUFSFRIST_TAGE
    assert daten["belehrung"]["ist_platzhalter"] is True
    assert daten["belehrung"]["version"] == vs.BELEHRUNG_PLATZHALTER_VERSION
    assert "PLATZHALTER" in daten["belehrung"]["text"] and "Rechtsberatung" in daten["belehrung"]["text"]
    assert "Muster-Widerrufsformular" in daten["widerrufsformular_text"]
    assert "PLATZHALTER" in daten["widerrufsformular_text"]


async def test_eigener_belehrungstext_mit_version_ersetzt_den_platzhalter(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten={**B2C, "widerrufsbelehrung_text": "Unser Text.\n\nZweiter Absatz.", "widerrufsbelehrung_version": "2026-10"},
    )

    daten = await _belehrung(client, ctx["h"])

    assert daten["belehrung"]["ist_platzhalter"] is False
    assert daten["belehrung"]["text"] == "Unser Text.\n\nZweiter Absatz."
    assert daten["belehrung"]["version"].startswith("2026-10#")

    # Textaenderung ohne neue Versionsnummer aendert trotzdem die ausgelieferte Version.
    await _firmendaten(ctx["mandant"], widerrufsbelehrung_text="Geaenderter Text.")
    assert (await _belehrung(client, ctx["h"]))["belehrung"]["version"] != daten["belehrung"]["version"]

    r = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}",
        headers=ctx["h"],
        json=_b2c_body(daten["belehrung"]["version"]),
    )
    assert r.status_code == 422  # Kunde hat noch die alte Fassung gesehen


async def test_b2c_annahme_speichert_belehrung_und_sendet_bestaetigung_mit_pdf(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)

    body = await _b2c_annehmen(client, ctx)

    assert body["status"] == "angenommen"
    assert body["verbraucherschutz"] is True
    (nachweis,) = await _nachweise(ctx["angebot_id"])
    assert nachweis.b2c_flag is True
    assert nachweis.belehrung_version == vs.BELEHRUNG_PLATZHALTER_VERSION
    assert "PLATZHALTER" in nachweis.belehrung_text
    assert body["nachweis_referenz"] == str(nachweis.id)

    (mail,) = mails
    assert mail["to"] == "portal@example.de"
    assert mail["subject"].startswith("Bestätigung Ihrer Beauftragung")
    assert str(nachweis.id) in mail["body"]  # Nachweis-Referenz
    assert "Widerrufsbelehrung" in mail["body"] and "Muster-Widerrufsformular" in mail["body"]
    assert "416,50" in mail["body"]  # 2*100 + 3*50 = 350 netto, 19 % -> 416,50 brutto
    dateiname, inhalt, mimetype = mail["attachment"]
    assert dateiname.endswith(".pdf") and mimetype == "application/pdf" and inhalt.startswith(b"%PDF")

    async with system_session() as session:
        logs = (await session.execute(select(EmailLog).where(EmailLog.entity_id == uuid.UUID(ctx["angebot_id"])))).scalars().all()
    assert [(log.status, log.anhang_dateiname) for log in logs] == [("gesendet", dateiname)]


async def test_mailfehler_macht_die_annahme_nicht_rueckgaengig_wird_aber_geloggt(
    client, make_mandant, make_user, make_kunde, monkeypatch, caplog
):
    async def _kaputt(session, mandant_id, **kwargs):
        raise RuntimeError("SMTP kaputt")

    monkeypatch.setattr("app.services.email_service.send_email", _kaputt)
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    # alembic/env.py ruft fileConfig() (disable_existing_loggers) in der
    # Session-Fixture auf und schaltet bereits importierte Logger stumm.
    logging.getLogger("app.services.angebot_annahme_service").disabled = False

    with caplog.at_level(logging.WARNING):
        body = await _b2c_annehmen(client, ctx)

    assert body["status"] == "angenommen"
    assert len(await _nachweise(ctx["angebot_id"])) == 1
    assert any("nicht versendet" in r.message and "SMTP kaputt" in r.message for r in caplog.records)
    async with system_session() as session:
        (log,) = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == uuid.UUID(ctx["angebot_id"])))
        ).scalars().all()
    assert log.status == "fehler" and "SMTP kaputt" in log.fehlermeldung


async def test_annahme_ohne_konfiguriertes_smtp_klappt(client, make_mandant, make_user, make_kunde):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)  # kein mails-Fixture: echter Pfad

    body = await _b2c_annehmen(client, ctx)

    assert body["status"] == "angenommen"
    async with system_session() as session:
        (log,) = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == uuid.UUID(ctx["angebot_id"])))
        ).scalars().all()
    assert log.status == "fehler"


# --- Widerruf ---------------------------------------------------------------------------------


async def _widerruf(client, ctx, **body):
    return await client.post(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}/widerruf",
        headers={**ctx["h"], "User-Agent": "WiderrufBrowser/2"},
        json={"bestaetigung": True, **body},
    )


async def test_widerruf_setzt_status_schreibt_nachweis_und_benachrichtigt(
    client, make_mandant, make_user, make_kunde, make_vorgang, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    body = await _b2c_annehmen(client, ctx)
    assert body["widerruf_moeglich"] is True
    assert body["widerruf_frist_bis"] is not None
    mails.clear()

    r = await _widerruf(client, ctx)

    assert r.status_code == 200, r.text
    antwort = r.json()
    assert antwort["status"] == "widerrufen" and antwort["widerrufen_am"] is not None
    assert antwort["widerruf_moeglich"] is False
    nachweise = await _nachweise(ctx["angebot_id"])
    assert [n.aktion for n in nachweise] == ["annahme", "widerruf"]
    assert nachweise[1].b2c_flag is True and nachweise[1].user_agent == "WiderrufBrowser/2"
    assert nachweise[1].zugang_email == "portal@example.de"
    assert nachweise[1].fassung_sha256 == nachweise[0].fassung_sha256

    # Eingangsbestaetigung an den Kunden + Hinweis-Mail an den Betrieb
    empfaenger = {m["to"]: m for m in mails}
    assert empfaenger["portal@example.de"]["subject"].startswith("Eingangsbestätigung Ihres Widerrufs")
    assert str(nachweise[1].id) in empfaenger["portal@example.de"]["body"]
    assert ctx["admin"].email in empfaenger and "widerrufen" in empfaenger[ctx["admin"].email]["body"]

    async with system_session() as session:
        benachrichtigungen = (
            await session.execute(select(Notification).where(Notification.ref_entity_id == uuid.UUID(ctx["angebot_id"])))
        ).scalars().all()
    assert ctx["admin"].id in {n.user_id for n in benachrichtigungen}
    assert all("widerrufen" in n.titel for n in benachrichtigungen)

    office = (await client.get(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"])).json()
    assert office["status"] == "widerrufen" and office["widerrufen_am"] is not None
    assert office["letzter_nachweis"]["aktion"] == "widerruf"


async def test_widerruf_vermerkt_ereignis_am_entstandenen_auftrag(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _b2c_annehmen(client, ctx)
    angebot = (await client.get(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"])).json()
    auftrag_id = angebot["auftrag_vorgang_id"]
    assert auftrag_id

    assert (await _widerruf(client, ctx)).status_code == 200

    async with system_session() as session:
        events = (
            await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == uuid.UUID(auftrag_id)))
        ).scalars().all()
    assert any("widerrufen" in (e.body or "") and e.author_user_id is None for e in events)


async def test_widerruf_braucht_ausdrueckliche_bestaetigung(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _b2c_annehmen(client, ctx)
    url = f"/api/kundenportal/angebote/{ctx['angebot_id']}/widerruf"

    assert (await client.post(url, headers=ctx["h"], json={})).status_code == 422
    assert (await client.post(url, headers=ctx["h"], json={"bestaetigung": False})).status_code == 422
    assert [n.aktion for n in await _nachweise(ctx["angebot_id"])] == ["annahme"]


async def test_zweiter_widerruf_und_widerruf_ohne_annahme_sind_409(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    assert (await _widerruf(client, ctx)).status_code == 409  # noch versendet, nicht angenommen
    await _b2c_annehmen(client, ctx)
    assert (await _widerruf(client, ctx)).status_code == 200
    zweiter = await _widerruf(client, ctx)
    assert zweiter.status_code == 409 and "bereits widerrufen" in zweiter.json()["detail"]


async def test_widerruf_nicht_moeglich_bei_b2b_annahme(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "angenommen"}
    )

    r = await _widerruf(client, ctx)

    assert r.status_code == 409 and "kein Widerrufsrecht" in r.json()["detail"]
    portal = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert portal["widerruf_moeglich"] is False and portal["widerruf_frist_bis"] is None


async def test_widerrufsfrist_14_tage(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _b2c_annehmen(client, ctx)

    async def annahme_vor(tage: int) -> None:
        async with system_session() as session:
            angebot = await session.get(Angebot, uuid.UUID(ctx["angebot_id"]))
            angebot.angenommen_am = datetime.now(timezone.utc) - timedelta(days=tage)

    await annahme_vor(15)
    r = await _widerruf(client, ctx)
    assert r.status_code == 409 and "Widerrufsfrist" in r.json()["detail"]
    portal = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert portal["widerruf_moeglich"] is False and "Widerrufsfrist" in portal["widerruf_hinweis"]

    await annahme_vor(13)
    assert (await _widerruf(client, ctx)).status_code == 200


def test_widerrufsfrist_endet_mit_ablauf_des_14_tages_in_lokaler_zeit():
    # Annahme 01.03.2026 23:30 Ortszeit (22:30 UTC): Tag 14 ist der 15.03.; die
    # Frist laeuft bis 16.03. 00:00 Ortszeit (= 15.03. 23:00 UTC).
    angenommen = datetime(2026, 3, 1, 22, 30, tzinfo=timezone.utc)
    assert vs.widerrufsfrist_ende(angenommen) == datetime(2026, 3, 15, 23, 0, tzinfo=timezone.utc)
    # Am Morgen desselben Tages ergibt sich dieselbe Frist.
    assert vs.widerrufsfrist_ende(datetime(2026, 3, 1, 5, 0, tzinfo=timezone.utc)) == datetime(
        2026, 3, 15, 23, 0, tzinfo=timezone.utc
    )


async def _rechnung(ctx, *, status, **kwargs) -> None:
    async with system_session() as session:
        session.add(
            Rechnung(
                mandant_id=ctx["mandant"].id,
                kunde_id=ctx["kunde"].id,
                rechnungsnummer=f"R-{uuid.uuid4().hex[:6]}",
                status=status,
                betrag_netto=Decimal("100"),
                erstellt_von=ctx["admin"].id,
                **kwargs,
            )
        )


async def test_widerruf_409_wenn_rechnung_zum_angebot_versendet(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _b2c_annehmen(client, ctx)
    await _rechnung(ctx, status="entwurf", angebot_id=uuid.UUID(ctx["angebot_id"]))

    # Entwurf blockiert nicht, das Portal zeigt den Button weiter
    portal = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert portal["widerruf_moeglich"] is True

    await _rechnung(ctx, status="versendet", angebot_id=uuid.UUID(ctx["angebot_id"]))
    r = await _widerruf(client, ctx)

    assert r.status_code == 409
    assert "Rechnung" in r.json()["detail"] and "Betrieb" in r.json()["detail"]
    portal = (await client.get(f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"])).json()
    assert portal["status"] == "angenommen" and portal["widerruf_moeglich"] is False
    assert "Betrieb" in portal["widerruf_hinweis"]
    assert [n.aktion for n in await _nachweise(ctx["angebot_id"])] == ["annahme"]


async def test_widerruf_409_wenn_rechnung_am_entstandenen_auftrag_versendet(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _b2c_annehmen(client, ctx)
    auftrag_id = (await client.get(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"])).json()[
        "auftrag_vorgang_id"
    ]
    await _rechnung(ctx, status="bezahlt", vorgang_id=uuid.UUID(auftrag_id))

    assert (await _widerruf(client, ctx)).status_code == 409


async def test_widerrufenes_angebot_laesst_sich_nicht_abrechnen_und_nicht_per_patch_setzen(
    client, make_mandant, make_user, make_kunde, mails
):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde)
    # Vor dem Widerruf: Staff darf den Status nicht frei auf "widerrufen" setzen.
    r = await client.patch(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"], json={"status": "widerrufen"})
    assert r.status_code == 400
    await _b2c_annehmen(client, ctx)
    r = await client.patch(f"/api/angebote/{ctx['angebot_id']}", headers=ctx["admin_h"], json={"status": "widerrufen"})
    assert r.status_code == 400

    assert (await _widerruf(client, ctx)).status_code == 200
    rechnung = await client.post(
        "/api/rechnungen/aus-angebot", headers=ctx["admin_h"], json={"angebot_id": ctx["angebot_id"], "rechnungsart": "rechnung", "leistungsdatum": "2026-08-10"},
    )
    assert rechnung.status_code == 400 and "angenommene" in rechnung.text
    kunde_antwort = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json={"status": "angenommen"}
    )
    assert kunde_antwort.status_code == 422  # B2C: ohne Pflichtfelder; mit Pflichtfeldern 400 (kein Statuswechsel)
    version = (await _belehrung(client, ctx["h"]))["belehrung"]["version"]
    nochmal = await client.patch(
        f"/api/kundenportal/angebote/{ctx['angebot_id']}", headers=ctx["h"], json=_b2c_body(version)
    )
    assert nochmal.status_code == 400


# --- Mandantentrennung ------------------------------------------------------------------------


async def test_fremde_angebote_sind_fuer_annahme_und_widerruf_404(
    client, make_mandant, make_user, make_kunde, mails
):
    a = await _aufbau(client, make_mandant, make_user, make_kunde, email="a@example.de")
    # Zweiter Kunde im selben Mandanten
    zweiter = await make_kunde(mandant=a["mandant"], name="Nachbar", typ="privat")
    await _make_zugang(a["mandant"], zweiter, email="nachbar@example.de")
    nachbar_h = auth_headers((await _kunden_login(client, "nachbar@example.de", "kunden-pw-123"))["access_token"])
    # Anderer Mandant
    b = await _aufbau(client, make_mandant, make_user, make_kunde, email="b@example.de")
    await _b2c_annehmen(client, a)

    for headers in (nachbar_h, b["h"]):
        annahme = await client.patch(
            f"/api/kundenportal/angebote/{a['angebot_id']}",
            headers=headers,
            json={"status": "angenommen", "bestaetigung": True, "belehrung_version": vs.BELEHRUNG_PLATZHALTER_VERSION},
        )
        widerruf = await client.post(
            f"/api/kundenportal/angebote/{a['angebot_id']}/widerruf", headers=headers, json={"bestaetigung": True}
        )
        assert annahme.status_code == 404 and widerruf.status_code == 404

    assert [n.aktion for n in await _nachweise(a["angebot_id"])] == ["annahme"]
    assert await _nachweise(b["angebot_id"]) == []


async def test_nachweis_tabelle_ist_append_only_und_mandantengetrennt(
    client, make_mandant, make_user, make_kunde, mails
):
    a = await _aufbau(client, make_mandant, make_user, make_kunde, email="a2@example.de")
    b = await _aufbau(client, make_mandant, make_user, make_kunde, email="b2@example.de")
    await _b2c_annehmen(client, a)
    await _b2c_annehmen(client, b)
    (nachweis_a,) = await _nachweise(a["angebot_id"])

    # UPDATE/DELETE schlagen laut Trigger fehl -- auch fuer die eigene Zeile und
    # auch mit Super-Admin-Rechten (system_session).
    for mandant_ctx in (
        lambda: tenant_session(mandant_id=a["mandant"].id, is_super_admin=False),
        lambda: system_session(),
    ):
        for sql in (
            "UPDATE angebot_annahmen SET ip = 'manipuliert' WHERE id = :id",
            "DELETE FROM angebot_annahmen WHERE id = :id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with mandant_ctx() as session:
                    await session.execute(text(sql), {"id": nachweis_a.id})

    # RLS: Mandant B sieht die Zeile von A nicht, kann sie nicht aendern und nicht fuer A einfuegen.
    async with tenant_session(mandant_id=b["mandant"].id, is_super_admin=False) as session:
        assert (await session.execute(select(AngebotAnnahme.id))).scalars().all() != []
        sichtbar = (await session.execute(select(AngebotAnnahme).where(AngebotAnnahme.id == nachweis_a.id))).all()
        assert sichtbar == []
        geaendert = await session.execute(text("UPDATE angebot_annahmen SET ip = 'x' WHERE id = :id"), {"id": nachweis_a.id})
        assert geaendert.rowcount == 0
    with pytest.raises(DBAPIError):
        async with tenant_session(mandant_id=b["mandant"].id, is_super_admin=False) as session:
            session.add(
                AngebotAnnahme(
                    mandant_id=a["mandant"].id, angebot_id=nachweis_a.angebot_id, aktion="annahme",
                    zugang_email="x@example.de", zugang_name="x", ip="1.1.1.1", fassung_sha256="0" * 64,
                )
            )
            await session.flush()

    (unveraendert,) = await _nachweise(a["angebot_id"])
    assert unveraendert.ip == "127.0.0.1"


async def test_aktion_und_hashlaenge_werden_von_der_datenbank_geprueft(client, make_mandant, make_user, make_kunde, mails):
    ctx = await _aufbau(client, make_mandant, make_user, make_kunde, kunde_typ="gewerbe")
    basis = dict(
        mandant_id=ctx["mandant"].id, angebot_id=uuid.UUID(ctx["angebot_id"]), zugang_email="x@example.de",
        zugang_name="x", ip="1.1.1.1",
    )
    for abweichung in ({"aktion": "loeschen", "fassung_sha256": "0" * 64}, {"aktion": "annahme", "fassung_sha256": "abc"}):
        with pytest.raises(DBAPIError):
            async with system_session() as session:
                session.add(AngebotAnnahme(**basis, **abweichung))
                await session.flush()


# --- Migration 0111 ---------------------------------------------------------------------------


async def test_migration_0111_up_down_up(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    engine = _sync_engine()
    angebot_id = uuid.uuid4()
    try:
        await _migrieren("downgrade", "0110")
        assert "widerrufen_am" not in _spalten(engine, "angebote")
        with engine.begin() as conn:
            vorhanden = conn.execute(text("SELECT to_regclass('angebot_annahmen')")).scalar()
            assert vorhanden is None
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(
                text(
                    "INSERT INTO angebote (id, mandant_id, kunde_id, angebotsnummer, status, erstellt_von) "
                    "VALUES (:id, :m, :k, 'A-MIG-0111', 'angenommen', :u)"
                ),
                {"id": angebot_id, "m": mandant.id, "k": kunde.id, "u": user.id},
            )

        await _migrieren("upgrade", "head")

        assert _spalten(engine, "angebote")["widerrufen_am"]["nullable"] is True
        assert {"fassung_sha256", "b2c_flag", "belehrung_version", "kunden_portal_zugang_id"} <= set(
            _spalten(engine, "angebot_annahmen")
        )
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            assert conn.execute(
                text("SELECT status FROM angebote WHERE id = :id"), {"id": angebot_id}
            ).scalar() == "angenommen"
            # Der neue Status ist jetzt erlaubt
            conn.execute(text("UPDATE angebote SET status = 'widerrufen' WHERE id = :id"), {"id": angebot_id})
            assert conn.execute(
                text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'angebot_annahmen'")
            ).scalar() is True
            assert conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_angebot_annahmen_append_only'")
            ).scalar() == 1

        # Downgrade mit widerrufenem Angebot und vorhandenem Nachweis: Status faellt auf 'angenommen' zurueck.
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(
                text(
                    "INSERT INTO angebot_annahmen (mandant_id, angebot_id, aktion, zugang_email, zugang_name, ip, "
                    "fassung_sha256) VALUES (:m, :a, 'widerruf', 'x@example.de', 'x', '1.1.1.1', :h)"
                ),
                {"m": mandant.id, "a": angebot_id, "h": "0" * 64},
            )
        await _migrieren("downgrade", "0110")
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            assert conn.execute(
                text("SELECT status FROM angebote WHERE id = :id"), {"id": angebot_id}
            ).scalar() == "angenommen"
            assert conn.execute(text("SELECT to_regclass('angebot_annahmen')")).scalar() is None
            with pytest.raises(Exception):
                conn.execute(text("UPDATE angebote SET status = 'widerrufen' WHERE id = :id"), {"id": angebot_id})
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


# --- Einstellungen, Mandanten-Default, Barrierefreiheit ----------------------------------------


async def test_neuer_mandant_startet_mit_nur_privatkunden(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    r = await client.post(
        "/api/admin/mandanten", headers=auth_headers(token), json={"name": "Frisch GmbH", "slug": "frisch-gmbh"}
    )

    assert r.status_code == 201
    async with system_session() as session:
        mandant = (await session.execute(select(Mandant).where(Mandant.slug == "frisch-gmbh"))).scalar_one()
    assert mandant.firmendaten["portal_verbraucherschutz"] == "nur_privatkunden"
    assert vs.modus(mandant) == "nur_privatkunden"


async def test_bestandsmandant_ohne_schluessel_gilt_als_aus(make_mandant):
    mandant = await make_mandant()
    assert vs.modus(mandant) == "aus"
    mandant.firmendaten = {"portal_verbraucherschutz": "kaputt"}
    assert vs.modus(mandant) == "aus"


async def test_einstellungen_speichern_und_validieren_portal_felder(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))

    ok = await client.patch(
        "/api/mandant/einstellungen",
        headers=h,
        json={
            "firmendaten": {
                "portal_verbraucherschutz": "nur_privatkunden",
                "widerrufsbelehrung_text": "  Text\n\nAbsatz  ",
                "widerrufsbelehrung_version": "2026-10-19",
                "barrierefreiheit_kontakt_email": "barrierefrei@beispiel.de",
                "barrierefreiheit_stand": "2026-10-19",
                "barrierefreiheit_url": "https://beispiel.de/barrierefreiheit",
            }
        },
    )
    assert ok.status_code == 200, ok.text
    fd = ok.json()["firmendaten"]
    assert fd["widerrufsbelehrung_text"] == "Text\n\nAbsatz"
    assert fd["portal_verbraucherschutz"] == "nur_privatkunden"

    for falsch in (
        {"portal_verbraucherschutz": "immer"},
        {"barrierefreiheit_kontakt_email": "keine-mail"},
        {"barrierefreiheit_stand": "gestern"},
        {"barrierefreiheit_url": "javascript:alert(1)"},
        {"widerrufsbelehrung_text": "x" * 20001},
    ):
        r = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": falsch})
        assert r.status_code == 422, falsch


async def test_public_rechtliches_liefert_barrierefreiheit_angaben(client, make_mandant):
    mandant = await make_mandant(name="Mueller Elektro")
    await _firmendaten(
        mandant,
        barrierefreiheit_url="https://mueller.de/barrierefreiheit",
        barrierefreiheit_kontakt_email="bf@mueller.de",
        barrierefreiheit_stand="2026-10-19",
    )

    body = (await client.get("/api/public/rechtliches")).json()

    assert body["barrierefreiheit_url"] == "https://mueller.de/barrierefreiheit"
    assert body["barrierefreiheit_kontakt_email"] == "bf@mueller.de"
    assert body["barrierefreiheit_stand"] == "2026-10-19"

    await _firmendaten(mandant, barrierefreiheit_url="javascript:alert(1)")
    assert (await client.get("/api/public/rechtliches")).json()["barrierefreiheit_url"] is None
