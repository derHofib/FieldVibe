"""Tagesgrenzen der Zeiterfassung in Europe/Berlin statt UTC (app/core/zeit.py)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.zeit import in_lokal, tagesbeginn_utc, tagesende_utc
from app.db.session import system_session
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login

BERLIN = ZoneInfo("Europe/Berlin")


def test_tagesbeginn_sommer_und_winter():
    assert tagesbeginn_utc(date(2026, 7, 1)) == datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc)
    assert tagesbeginn_utc(date(2026, 1, 15)) == datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)


def test_umstellungstage_haben_23_bzw_25_stunden():
    # 29.03.2026 Sommerzeit-Beginn, 25.10.2026 Winterzeit-Beginn
    assert tagesende_utc(date(2026, 3, 29)) - tagesbeginn_utc(date(2026, 3, 29)) == timedelta(hours=23)
    assert tagesende_utc(date(2026, 10, 25)) - tagesbeginn_utc(date(2026, 10, 25)) == timedelta(hours=25)
    assert tagesende_utc(date(2026, 3, 29)) == tagesbeginn_utc(date(2026, 3, 30))


async def _eintrag(mandant, techniker, vorgang, lokal: datetime) -> None:
    start = lokal.replace(tzinfo=BERLIN).astimezone(timezone.utc)
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=techniker.id,
                start_at=start, ende_at=start + timedelta(minutes=30),
            )
        )
        await session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spaet,frueh,tag_spaet,tag_frueh",
    [
        # Sommerzeit-Umstellung 29.03.2026 (Mitternacht liegt noch vor der Umstellung)
        (datetime(2026, 3, 30, 23, 30), datetime(2026, 3, 31, 0, 30), date(2026, 3, 30), date(2026, 3, 31)),
        (datetime(2026, 3, 28, 23, 30), datetime(2026, 3, 29, 0, 30), date(2026, 3, 28), date(2026, 3, 29)),
        # Winterzeit-Umstellung 25.10.2026
        (datetime(2026, 10, 24, 23, 30), datetime(2026, 10, 25, 0, 30), date(2026, 10, 24), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 23, 30), datetime(2026, 10, 26, 0, 30), date(2026, 10, 25), date(2026, 10, 26)),
        # normale Winterzeit
        (datetime(2026, 1, 14, 23, 30), datetime(2026, 1, 15, 0, 30), date(2026, 1, 14), date(2026, 1, 15)),
    ],
)
async def test_eintraege_um_mitternacht_landen_am_richtigen_tag(
    client, make_mandant, make_user, make_kunde, make_vorgang, spaet, frueh, tag_spaet, tag_frueh
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _eintrag(mandant, admin, vorgang, spaet)
    await _eintrag(mandant, admin, vorgang, frueh)
    token = await login(client, admin.email, "pw-123456")

    async def _anzahl(tag: date) -> list[str]:
        resp = await client.get(
            "/api/zeiterfassung",
            headers=auth_headers(token),
            params={"von": tag.isoformat(), "bis": tag.isoformat()},
        )
        assert resp.status_code == 200
        return [e["start_at"] for e in resp.json()]

    spaet_utc = spaet.replace(tzinfo=BERLIN).astimezone(timezone.utc)
    frueh_utc = frueh.replace(tzinfo=BERLIN).astimezone(timezone.utc)
    assert [datetime.fromisoformat(s) for s in await _anzahl(tag_spaet)] == [spaet_utc]
    assert [datetime.fromisoformat(s) for s in await _anzahl(tag_frueh)] == [frueh_utc]


@pytest.mark.asyncio
async def test_wochenfilter_montag_bis_sonntag_lokal(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    # Woche Mo 23.03. - So 29.03.2026 (Umstellung am Sonntag)
    await _eintrag(mandant, admin, vorgang, datetime(2026, 3, 22, 23, 30))  # Sonntag davor: raus
    await _eintrag(mandant, admin, vorgang, datetime(2026, 3, 23, 0, 30))  # Montag fruehestens: drin
    await _eintrag(mandant, admin, vorgang, datetime(2026, 3, 29, 23, 30) - timedelta(hours=1))  # So: drin
    await _eintrag(mandant, admin, vorgang, datetime(2026, 3, 30, 0, 30))  # Montag danach: raus
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/zeiterfassung",
        headers=auth_headers(token),
        params={"von": "2026-03-23", "bis": "2026-03-29"},
    )
    assert resp.status_code == 200
    lokale = sorted(in_lokal(datetime.fromisoformat(e["start_at"])).replace(tzinfo=None) for e in resp.json())
    assert lokale == [datetime(2026, 3, 23, 0, 30), datetime(2026, 3, 29, 22, 30)]
