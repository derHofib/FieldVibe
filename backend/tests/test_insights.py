from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.rechnung import Rechnung
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_non_admin_roles_cannot_access_insights(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="t@example.de")

    disponent_token = await login(client, disponent.email, "pw-123456")
    resp = await client.get("/api/insights", headers=auth_headers(disponent_token))
    assert resp.status_code == 403

    techniker_token = await login(client, techniker.email, "pw-123456")
    resp = await client.get("/api/insights", headers=auth_headers(techniker_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_insights_aggregation_correctness(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="tech@example.de")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")

    async with system_session() as session:
        session.add_all(
            [
                Rechnung(
                    mandant_id=mandant.id,
                    kunde_id=kunde.id,
                    rechnungsnummer="R-INS-1",
                    betrag_netto=Decimal("100.00"),
                    mwst_satz=Decimal("19.00"),
                    status="versendet",
                    erstellt_von=admin.id,
                ),
                Rechnung(
                    mandant_id=mandant.id,
                    kunde_id=kunde.id,
                    rechnungsnummer="R-INS-2",
                    betrag_netto=Decimal("50.00"),
                    mwst_satz=Decimal("19.00"),
                    status="bezahlt",
                    erstellt_von=admin.id,
                ),
            ]
        )
        await session.commit()

    vorgang_fuer_zeit = await make_vorgang(mandant=mandant, kunde=kunde)
    jetzt = datetime.now(timezone.utc)
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang_fuer_zeit.id,
                techniker_id=techniker.id,
                start_at=jetzt - timedelta(hours=2),
                ende_at=jetzt,
            )
        )
        await session.commit()

    admin_token = await login(client, admin.email, "pw-123456")

    angebot1 = await client.post(
        "/api/angebote",
        headers=auth_headers(admin_token),
        json={"kunde_id": str(kunde.id), "positionen": [{"beschreibung": "x", "einzelpreis": "1"}]},
    )
    angebot1_id = angebot1.json()["id"]
    await client.patch(
        f"/api/angebote/{angebot1_id}", headers=auth_headers(admin_token), json={"status": "versendet"}
    )
    await client.patch(
        f"/api/angebote/{angebot1_id}", headers=auth_headers(admin_token), json={"status": "angenommen"}
    )

    angebot2 = await client.post(
        "/api/angebote",
        headers=auth_headers(admin_token),
        json={"kunde_id": str(kunde.id), "positionen": [{"beschreibung": "y", "einzelpreis": "1"}]},
    )
    angebot2_id = angebot2.json()["id"]
    await client.patch(
        f"/api/angebote/{angebot2_id}", headers=auth_headers(admin_token), json={"status": "versendet"}
    )

    resp = await client.get("/api/insights", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    body = resp.json()

    # 2 explizit "neu" + der Vorgang, der unten fuer die Zeiterfassung angelegt
    # wird (make_vorgang() faellt sonst auf den Modell-Default "neu" zurueck)
    assert body["vorgaenge_nach_status"]["neu"] == 3
    assert body["vorgaenge_nach_status"]["abgeschlossen"] == 1

    # Nur die "versendet" Rechnung zaehlt zur offenen Summe (100 * 1.19 = 119.00),
    # die bereits bezahlte nicht.
    assert body["offene_rechnungssumme"] == "119.00"

    assert body["angebote_versendet"] == 2
    assert body["angebote_angenommen"] == 1
    assert body["angebote_annahmequote"] == pytest.approx(0.5)

    techniker_eintrag = next(
        t for t in body["techniker_auslastung"] if t["techniker_id"] == str(techniker.id)
    )
    assert techniker_eintrag["stunden_diese_woche"] == "2.0"


@pytest.mark.asyncio
async def test_insights_offene_verbindlichkeiten(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    offen = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
            "mwst_satz": "19.00",
        },
    )
    # Teilweise bezahlt -- nur der Restbetrag darf in die offene Summe einfliessen.
    await client.post(
        f"/api/eingangsrechnungen/{offen.json()['id']}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "19.00"},
    )

    bezahlt = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-2",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "50.00",
            "mwst_satz": "19.00",
        },
    )
    await client.post(
        f"/api/eingangsrechnungen/{bezahlt.json()['id']}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "59.50"},
    )

    resp = await client.get("/api/insights", headers=auth_headers(token))
    assert resp.status_code == 200
    # 119.00 - 19.00 = 100.00 offen fuer RE-1, RE-2 ist vollstaendig bezahlt.
    assert resp.json()["offene_verbindlichkeiten"] == "100.00"


@pytest.mark.asyncio
async def test_insights_annahmequote_null_ohne_versendete_angebote(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/insights", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["angebote_annahmequote"] is None


@pytest.mark.asyncio
async def test_mandant_isolation_for_insights(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    await make_vorgang(mandant=mandant1, kunde=kunde1, status="neu")

    token2 = await login(client, admin2.email, "pw-123456")
    resp = await client.get("/api/insights", headers=auth_headers(token2))
    assert resp.json()["vorgaenge_nach_status"] == {}
