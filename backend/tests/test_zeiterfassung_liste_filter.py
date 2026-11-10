"""GET /api/zeiterfassung: zusaetzliche Filter fuer die Seite "Zeiten
buchen" (docs/konzepte/ZEITERFASSUNG.md Abschnitt 7.3) -- kunde_id/
auftrag_id/projekt_id, laufend, vermerkt_aelter_als_tage, sowie die
transienten vorgang_kunde_id/_auftrag_id/_projekt_id-Felder."""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.session import system_session
from app.models.auftrag import Auftrag
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_filter_nach_auftrag_und_vorgang_kontext_felder(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        auftrag = Auftrag(mandant_id=mandant.id, kunde_id=kunde.id, titel="Testauftrag", erstellt_von=admin.id)
        session.add(auftrag)
        await session.flush()
        auftrag_id = auftrag.id

    vorgang_im_auftrag = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=auftrag_id)
    anderer_vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    async with system_session() as session:
        start = datetime.now(timezone.utc)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang_im_auftrag.id, techniker_id=admin.id,
                start_at=start, ende_at=start + timedelta(hours=1), kategorie="auftrag",
            )
        )
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=anderer_vorgang.id, techniker_id=admin.id,
                start_at=start, ende_at=start + timedelta(hours=1), kategorie="auftrag",
            )
        )
        await session.flush()

    resp = await client.get(
        f"/api/zeiterfassung?auftrag_id={auftrag_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["vorgangsnummer"] == vorgang_im_auftrag.vorgangsnummer
    assert body[0]["vorgang_kunde_id"] == str(kunde.id)
    assert body[0]["vorgang_auftrag_id"] == str(auftrag_id)
    assert body[0]["vorgang_projekt_id"] is None

    resp_kunde = await client.get(
        f"/api/zeiterfassung?kunde_id={kunde.id}", headers=auth_headers(token)
    )
    assert len(resp_kunde.json()) == 2


@pytest.mark.asyncio
async def test_filter_laufend(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        start = datetime.now(timezone.utc)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=admin.id,
                start_at=start, ende_at=start + timedelta(hours=1), kategorie="auftrag",
            )
        )
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=admin.id,
                start_at=start, ende_at=None, kategorie="auftrag",
            )
        )
        await session.flush()

    laufend = await client.get("/api/zeiterfassung?laufend=true", headers=auth_headers(token))
    assert len(laufend.json()) == 1
    assert laufend.json()[0]["ende_at"] is None

    nicht_laufend = await client.get("/api/zeiterfassung?laufend=false", headers=auth_headers(token))
    assert len(nicht_laufend.json()) == 1
    assert nicht_laufend.json()[0]["ende_at"] is not None


@pytest.mark.asyncio
async def test_filter_vermerkt_aelter_als_tage(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        alt_start = datetime.now(timezone.utc) - timedelta(days=10)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=admin.id,
                start_at=alt_start, ende_at=alt_start + timedelta(hours=1), kategorie="auftrag",
                buchungsstatus="vermerkt",
            )
        )
        neu_start = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=admin.id,
                start_at=neu_start, ende_at=neu_start + timedelta(minutes=30), kategorie="auftrag",
                buchungsstatus="vermerkt",
            )
        )
        # Alt, aber schon gebucht -- darf nicht als "aelter als X Tage
        # vermerkt" auftauchen.
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang.id, techniker_id=admin.id,
                start_at=alt_start, ende_at=alt_start + timedelta(hours=1), kategorie="auftrag",
                buchungsstatus="gebucht",
            )
        )
        await session.flush()

    resp = await client.get(
        "/api/zeiterfassung?vermerkt_aelter_als_tage=5", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["buchungsstatus"] == "vermerkt"
