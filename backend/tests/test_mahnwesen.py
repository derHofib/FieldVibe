import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.email_log import EmailLog
from app.models.mandant import Mandant
from app.models.notification import Notification
from app.models.rechnung import Rechnung
from app.models.vorgang_event import VorgangEvent
from app.services.mahnwesen_service import berechne_verzugszinsen, run_mahnwesen_eskalation


async def _setze_firmendaten(mandant, firmendaten: dict) -> None:
    async with system_session() as session:
        m = await session.get(Mandant, mandant.id)
        m.firmendaten = firmendaten
        await session.flush()


async def _make_rechnung(mandant, kunde, ersteller, *, faellig_vor_tagen: int | None, status: str = "versendet", **kwargs):
    async with system_session() as session:
        rechnung = Rechnung(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            rechnungsnummer=kwargs.pop("rechnungsnummer", f"R-{uuid.uuid4().hex[:8]}"),
            betrag_netto=Decimal("100.00"),
            status=status,
            erstellt_von=ersteller.id,
            faellig_am=(date.today() - timedelta(days=faellig_vor_tagen)) if faellig_vor_tagen is not None else None,
            **kwargs,
        )
        session.add(rechnung)
        await session.flush()
        await session.refresh(rechnung)
        return rechnung


@pytest.mark.asyncio
async def test_ueberfaellige_rechnung_eskaliert_auf_stufe_1(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=15, vorgang_id=vorgang.id)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 1

    async with system_session() as session:
        refreshed = await session.get(Rechnung, rechnung.id)
        assert refreshed.mahnstufe == 1
        assert refreshed.letzte_mahnung_am is not None

        events = (
            await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))
        ).scalars().all()
        assert any("1. Mahnung" in (e.body or "") for e in events)

        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == admin.id))
        ).scalars().all()
        assert any(n.ref_entity_id == rechnung.id for n in notifications)


@pytest.mark.asyncio
async def test_wiederholter_lauf_ohne_stufenwechsel_eskaliert_nicht_erneut(
    make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=15)

    first = await run_mahnwesen_eskalation()
    assert first["rechnungen_eskaliert"] == 1

    second = await run_mahnwesen_eskalation()
    assert second["rechnungen_eskaliert"] == 0

    async with system_session() as session:
        refreshed = await session.get(Rechnung, rechnung.id)
        assert refreshed.mahnstufe == 1


@pytest.mark.asyncio
async def test_eskaliert_weiter_auf_stufe_2_bei_laengerer_ueberfaelligkeit(
    make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=29)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 1

    async with system_session() as session:
        refreshed = await session.get(Rechnung, rechnung.id)
        assert refreshed.mahnstufe == 2


@pytest.mark.asyncio
async def test_nicht_ueberfaellige_rechnung_wird_nicht_eskaliert(
    make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=5)
    await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=None)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 0


@pytest.mark.asyncio
async def test_mahnwesen_scoped_to_mandant_ids_ignores_others(
    make_mandant, make_user, make_kunde
):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin")
    kunde1 = await make_kunde(mandant=mandant1)
    kunde2 = await make_kunde(mandant=mandant2)
    rechnung1 = await _make_rechnung(mandant1, kunde1, admin1, faellig_vor_tagen=15)
    rechnung2 = await _make_rechnung(mandant2, kunde2, admin2, faellig_vor_tagen=15)

    ergebnis = await run_mahnwesen_eskalation(mandant_ids=[mandant1.id])
    assert ergebnis["rechnungen_eskaliert"] == 1

    async with system_session() as session:
        r1 = await session.get(Rechnung, rechnung1.id)
        r2 = await session.get(Rechnung, rechnung2.id)
        assert r1.mahnstufe == 1
        assert r2.mahnstufe == 0


@pytest.mark.asyncio
async def test_bezahlte_oder_stornierte_rechnung_wird_nicht_eskaliert(
    make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=100, status="bezahlt")
    await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=100, status="storniert")
    await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=100, status="entwurf")

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 0


@pytest.mark.asyncio
async def test_standard_ist_nur_interner_hinweis_kein_automatischer_versand(
    make_mandant, make_user, make_kunde
):
    """Ohne explizit aktivierten Auto-Versand (Standard) darf keine E-Mail
    an den Kunden gehen -- nur die interne Notification wie bisher."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant, ansprechpartner=[{"email": "kunde@example.de"}])
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=15)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 1
    assert ergebnis["automatisch_versendet"] == 0

    async with system_session() as session:
        logs = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == rechnung.id))
        ).scalars().all()
        assert logs == []


@pytest.mark.asyncio
async def test_mahnung_1_automatisch_versendet_email_mit_verzugszinsen(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    await _setze_firmendaten(mandant, {"mahnung_1_automatisch": True})
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(
        mandant=mandant, typ="gewerbe", ansprechpartner=[{"email": "kunde@example.de"}]
    )
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=15, vorgang_id=vorgang.id)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 1
    assert ergebnis["automatisch_versendet"] == 1

    async with system_session() as session:
        logs = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == rechnung.id))
        ).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.empfaenger == "kunde@example.de"
        assert "1. Mahnung" in log.betreff
        assert log.gesendet_von is None
        assert log.anhang_dateiname == f"Mahnung-{rechnung.rechnungsnummer}.pdf"

        events = (
            await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))
        ).scalars().all()
        assert any("automatisch per E-Mail versendet" in (e.body or "") for e in events)


@pytest.mark.asyncio
async def test_mahnung_2_automatisch_bleibt_ohne_wirkung_wenn_nur_stufe_1_aktiviert(
    make_mandant, make_user, make_kunde
):
    """Der Auto-Versand ist je Mahnstufe einzeln konfigurierbar -- ist nur
    Stufe 1 aktiviert, darf eine direkt auf Stufe 2 eskalierende Rechnung
    keine automatische Mahnung ausloesen."""
    mandant = await make_mandant()
    await _setze_firmendaten(mandant, {"mahnung_1_automatisch": True})
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant, ansprechpartner=[{"email": "kunde@example.de"}])
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=29)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["rechnungen_eskaliert"] == 1
    assert ergebnis["automatisch_versendet"] == 0

    async with system_session() as session:
        refreshed = await session.get(Rechnung, rechnung.id)
        assert refreshed.mahnstufe == 2
        logs = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == rechnung.id))
        ).scalars().all()
        assert logs == []


@pytest.mark.asyncio
async def test_automatischer_versand_ohne_kunden_email_faellt_auf_hinweis_zurueck(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    await _setze_firmendaten(mandant, {"mahnung_1_automatisch": True})
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    rechnung = await _make_rechnung(mandant, kunde, admin, faellig_vor_tagen=15, vorgang_id=vorgang.id)

    ergebnis = await run_mahnwesen_eskalation()
    assert ergebnis["automatisch_versendet"] == 0

    async with system_session() as session:
        logs = (
            await session.execute(select(EmailLog).where(EmailLog.entity_id == rechnung.id))
        ).scalars().all()
        assert logs == []
        events = (
            await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))
        ).scalars().all()
        assert any("fehlgeschlagen" in (e.body or "") for e in events)


def test_verzugszinsen_b2b_hoeher_als_b2c_bei_gleichem_betrag():
    betrag = Decimal("1000.00")
    zins_b2b = berechne_verzugszinsen(betrag, tage_ueberfaellig=30, ist_unternehmer=True)
    zins_b2c = berechne_verzugszinsen(betrag, tage_ueberfaellig=30, ist_unternehmer=False)
    assert zins_b2b > zins_b2c
    assert zins_b2b > Decimal("0")
