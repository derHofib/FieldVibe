"""Zeiterfassung Stufe 4 (docs/konzepte/ZEITERFASSUNG.md): Abrechnung --
Fahrzeit-/Fahrtkosten-Vorschlaege und das Sperren/Entsperren der
zugrunde liegenden Zeiterfassung-Eintraege beim Uebernehmen/Entfernen
einer Rechnungsposition."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


async def _fahrzeit_eintrag(
    session, *, mandant, vorgang, techniker, km: str = "42.0", stunden: float = 2.0
) -> Zeiterfassung:
    start = datetime.now(timezone.utc)
    eintrag = Zeiterfassung(
        mandant_id=mandant.id,
        vorgang_id=vorgang.id,
        techniker_id=techniker.id,
        start_at=start,
        ende_at=start + timedelta(hours=stunden),
        kategorie="fahrzeit",
        abrechenbar=True,
        buchungsstatus="gebucht",
        km=Decimal(km),
    )
    session.add(eintrag)
    await session.flush()
    await session.refresh(eintrag)
    return eintrag


@pytest.mark.asyncio
async def test_fahrzeit_abrechnung_keine_zeigt_keine_vorschlaege(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        await _fahrzeit_eintrag(session, mandant=mandant, vorgang=vorgang, techniker=admin)

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)},
    )
    resp = await client.get(
        f"/api/rechnungen/{created.json()['id']}/positionsvorschlaege", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    # Default fahrzeit_abrechnung="keine" -- keine Fahrzeit/Fahrtkosten-Box.
    assert all(v["quelle"] not in ("fahrzeit", "fahrtkosten") for v in resp.json())


@pytest.mark.asyncio
async def test_fahrzeit_und_fahrtkosten_vorschlaege_zeit_und_km(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    settings_resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"fahrzeit_abrechnung": "zeit_und_km", "km_satz_netto": "0.30"},
    )
    assert settings_resp.status_code == 200
    assert settings_resp.json()["fahrzeit_abrechnung"] == "zeit_und_km"
    assert settings_resp.json()["km_satz_netto"] == "0.30"

    async with system_session() as session:
        await _fahrzeit_eintrag(session, mandant=mandant, vorgang=vorgang, techniker=admin, km="50.0", stunden=2.0)

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)},
    )
    rechnung_id = created.json()["id"]
    resp = await client.get(f"/api/rechnungen/{rechnung_id}/positionsvorschlaege", headers=auth_headers(token))
    vorschlaege = resp.json()

    fahrzeit = next(v for v in vorschlaege if v["quelle"] == "fahrzeit")
    assert fahrzeit["beschreibung"] == "Fahrzeit"
    assert fahrzeit["menge"] == "2.00"
    assert fahrzeit["einheit"] == "Std"

    fahrtkosten = next(v for v in vorschlaege if v["quelle"] == "fahrtkosten")
    assert fahrtkosten["beschreibung"] == "Fahrtkosten"
    assert fahrtkosten["menge"] == "50.0"
    assert fahrtkosten["einheit"] == "km"
    assert fahrtkosten["einzelpreis"] == "0.30"


@pytest.mark.asyncio
async def test_add_position_fahrzeit_sperrt_zeiterfassung(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"fahrzeit_abrechnung": "zeit"}
    )

    async with system_session() as session:
        eintrag = await _fahrzeit_eintrag(session, mandant=mandant, vorgang=vorgang, techniker=admin)
        eintrag_id = eintrag.id

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)},
    )
    rechnung_id = created.json()["id"]

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Fahrzeit", "menge": "2", "einheit": "Std", "einzelpreis": "0", "quelle": "fahrzeit"},
    )
    assert resp.status_code == 200
    assert resp.json()["positionen"][0]["quelle"] == "fahrzeit"

    async with system_session() as session:
        aktualisiert = await session.get(Zeiterfassung, eintrag_id)
        assert aktualisiert.buchungsstatus == "abgerechnet"
        assert str(aktualisiert.abgerechnet_rechnung_id) == rechnung_id


@pytest.mark.asyncio
async def test_remove_position_ohne_geschwister_setzt_zeit_zurueck(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"fahrzeit_abrechnung": "zeit_und_km", "km_satz_netto": "0.30"},
    )

    async with system_session() as session:
        eintrag = await _fahrzeit_eintrag(session, mandant=mandant, vorgang=vorgang, techniker=admin)
        eintrag_id = eintrag.id

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)},
    )
    rechnung_id = created.json()["id"]

    fahrzeit_resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Fahrzeit", "menge": "2", "einheit": "Std", "einzelpreis": "0", "quelle": "fahrzeit"},
    )
    fahrzeit_position_id = next(
        p["id"] for p in fahrzeit_resp.json()["positionen"] if p["quelle"] == "fahrzeit"
    )
    fahrtkosten_resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={
            "beschreibung": "Fahrtkosten",
            "menge": "42",
            "einheit": "km",
            "einzelpreis": "0.30",
            "quelle": "fahrtkosten",
        },
    )
    fahrtkosten_position_id = next(
        p["id"] for p in fahrtkosten_resp.json()["positionen"] if p["quelle"] == "fahrtkosten"
    )

    # Erste Geschwister-Position entfernen: die andere braucht die Zeilen
    # noch, also bleibt der Eintrag gesperrt.
    remove_1 = await client.delete(
        f"/api/rechnungen/{rechnung_id}/positionen/{fahrzeit_position_id}", headers=auth_headers(token)
    )
    assert remove_1.status_code == 200
    async with system_session() as session:
        zwischenstand = await session.get(Zeiterfassung, eintrag_id)
        assert zwischenstand.buchungsstatus == "abgerechnet"

    # Letzte verbleibende Position entfernen: jetzt zurueck auf 'gebucht'.
    remove_2 = await client.delete(
        f"/api/rechnungen/{rechnung_id}/positionen/{fahrtkosten_position_id}", headers=auth_headers(token)
    )
    assert remove_2.status_code == 200
    async with system_session() as session:
        endstand = await session.get(Zeiterfassung, eintrag_id)
        assert endstand.buchungsstatus == "gebucht"
        assert endstand.abgerechnet_rechnung_id is None


@pytest.mark.asyncio
async def test_remove_position_nur_im_entwurf(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "50"},
    )
    rechnung_id = created.json()["id"]
    pos_resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Sonstiges", "menge": "1", "einheit": "Stk", "einzelpreis": "50"},
    )
    position_id = pos_resp.json()["positionen"][0]["id"]

    versendet = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versendet.status_code == 200

    resp = await client.delete(
        f"/api/rechnungen/{rechnung_id}/positionen/{position_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 400
