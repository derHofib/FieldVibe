from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.rechnung import Rechnung, RechnungPosition
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
    # + der Auftrag, den die Annahme von angebot1 (ohne Maengel, ohne Vorgang)
    # automatisch anlegt
    assert body["vorgaenge_nach_status"]["neu"] == 4
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


@pytest.mark.asyncio
async def test_insights_ignoriert_geloeschte_datensaetze(client, make_mandant, make_user, make_kunde, make_vorgang):
    """Jede Kennzahl: ein aktiver und ein soft-gelöschter Datensatz, nur der
    aktive darf auftauchen."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456", email="tech2@example.de")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    jetzt = datetime.now(timezone.utc)

    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu", geloescht_am=jetzt)
    await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen", geloescht_am=jetzt)
    vorgang_fuer_zeit = await make_vorgang(mandant=mandant, kunde=kunde, status="in_arbeit")

    async with system_session() as session:
        for nummer, geloescht in (("R-DEL-1", None), ("R-DEL-2", jetzt)):
            rechnung = Rechnung(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                rechnungsnummer=nummer,
                betrag_netto=Decimal("0"),
                mwst_satz=Decimal("19.00"),
                status="entwurf",
                erstellt_von=admin.id,
                geloescht_am=geloescht,
            )
            session.add(rechnung)
            await session.flush()
            session.add(
                RechnungPosition(
                    mandant_id=mandant.id,
                    rechnung_id=rechnung.id,
                    position=1,
                    beschreibung="Leistung",
                    menge=Decimal("1"),
                    einheit="psch",
                    einzelpreis=Decimal("100"),
                    steuer_kategorie="S",
                    steuer_satz=Decimal("19"),
                )
            )
        for nummer, geloescht in (("A-DEL-1", None), ("A-DEL-2", jetzt)):
            session.add(
                Angebot(
                    mandant_id=mandant.id,
                    kunde_id=kunde.id,
                    angebotsnummer=nummer,
                    status="angenommen",
                    versendet_am=jetzt,
                    angenommen_am=jetzt,
                    erstellt_von=admin.id,
                    geloescht_am=geloescht,
                )
            )
        for nummer, geloescht in (("E-DEL-1", None), ("E-DEL-2", jetzt)):
            session.add(
                Eingangsrechnung(
                    mandant_id=mandant.id,
                    lieferant_name="Sonepar",
                    rechnungsnummer_lieferant=nummer,
                    rechnungsdatum=date(2026, 8, 1),
                    betrag_netto=Decimal("50.00"),
                    mwst_satz=Decimal("19.00"),
                    status="offen",
                    geloescht_am=geloescht,
                )
            )
        for geloescht in (None, jetzt):
            session.add(
                Zeiterfassung(
                    mandant_id=mandant.id,
                    vorgang_id=vorgang_fuer_zeit.id,
                    techniker_id=techniker.id,
                    start_at=jetzt - timedelta(hours=2),
                    ende_at=jetzt - timedelta(hours=1),
                    geloescht_am=geloescht,
                )
            )
        await session.commit()

    resp = await client.get("/api/insights", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    assert body["vorgaenge_nach_status"] == {"neu": 1, "in_arbeit": 1}
    # Nur der aktive Entwurf: 100 * 1,19
    assert body["offene_rechnungssumme"] == "119.00"
    assert body["offene_verbindlichkeiten"] == "59.50"
    assert body["angebote_versendet"] == 1
    assert body["angebote_angenommen"] == 1
    eintrag = next(t for t in body["techniker_auslastung"] if t["techniker_id"] == str(techniker.id))
    assert eintrag["stunden_diese_woche"] == "1.0"
