"""Zeiterfassung Stufe 4 (docs/konzepte/ZEITERFASSUNG.md Abschnitt 7.4):
"Zeit"-Block im Auftrag-/Projekt-Panel -- Summen je Buchungsstatus."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.auftrag import Auftrag
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_zeit_summen_je_status_fuer_auftrag(
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

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=auftrag_id)
    anderer_vorgang = await make_vorgang(mandant=mandant, kunde=kunde)  # nicht Teil des Auftrags

    async with system_session() as session:
        start = datetime.now(timezone.utc)
        # Arbeitszeit "vermerkt" (2 Std)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang.id,
                techniker_id=admin.id,
                start_at=start,
                ende_at=start + timedelta(hours=2),
                kategorie="auftrag",
                abrechenbar=True,
                buchungsstatus="vermerkt",
            )
        )
        # Fahrzeit "gebucht" (1 Std, 30 km)
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang.id,
                techniker_id=admin.id,
                start_at=start,
                ende_at=start + timedelta(hours=1),
                kategorie="fahrzeit",
                abrechenbar=True,
                buchungsstatus="gebucht",
                km=Decimal("30.0"),
            )
        )
        # Zeit an einem NICHT zum Auftrag gehoerenden Vorgang -- darf nicht mitzaehlen.
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=anderer_vorgang.id,
                techniker_id=admin.id,
                start_at=start,
                ende_at=start + timedelta(hours=5),
                kategorie="auftrag",
                abrechenbar=True,
                buchungsstatus="vermerkt",
            )
        )
        await session.flush()

    resp = await client.get(
        f"/api/zeiterfassung/summen?auftrag_id={auftrag_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["vermerkt"]["arbeitszeit_stunden"] == "2.0"
    assert body["vermerkt"]["fahrzeit_stunden"] == "0.0"
    assert body["gebucht"]["fahrzeit_stunden"] == "1.0"
    assert body["gebucht"]["km"] == "30.0"
    assert body["abgerechnet"]["arbeitszeit_stunden"] == "0.0"


@pytest.mark.asyncio
async def test_zeit_summen_braucht_genau_ein_filter(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    ohne_filter = await client.get("/api/zeiterfassung/summen", headers=auth_headers(token))
    assert ohne_filter.status_code == 400

    import uuid

    beide = await client.get(
        f"/api/zeiterfassung/summen?auftrag_id={uuid.uuid4()}&projekt_id={uuid.uuid4()}",
        headers=auth_headers(token),
    )
    assert beide.status_code == 400
