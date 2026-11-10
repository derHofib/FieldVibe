from datetime import datetime, timedelta, timezone

import pytest

from app.db.session import system_session
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_manueller_eintrag_ohne_vorgang(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc).replace(microsecond=0)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=8)).isoformat(),
            "kategorie": "urlaub",
            "taetigkeit": "Sommerurlaub",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kategorie"] == "urlaub"
    assert body["vorgang_id"] is None
    assert body["vorgangsnummer"] is None
    # Ohne explizite Angabe soll abrechenbar bei Nicht-Auftrags-Kategorien
    # nicht automatisch True sein (siehe ZeiterfassungManuellCreate-Default).
    assert body["abrechenbar"] is False


@pytest.mark.asyncio
async def test_kategorie_auftrag_braucht_vorgang(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "auftrag",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ende_muss_nach_start_liegen(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start - timedelta(hours=1)).isoformat(),
            "kategorie": "sonstiges",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_manueller_eintrag_mit_vorgang(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=2)).isoformat(),
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang.id),
            "abrechenbar": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["vorgang_id"] == str(vorgang.id)
    assert body["vorgangsnummer"] == vorgang.vorgangsnummer


@pytest.mark.asyncio
async def test_eigenen_eintrag_bearbeiten_und_loeschen(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    create = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "verwaltung",
        },
    )
    eintrag_id = create.json()["id"]

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"taetigkeit": "Buero"},
    )
    assert patch.status_code == 200
    assert patch.json()["taetigkeit"] == "Buero"

    delete = await client.delete(f"/api/zeiterfassung/{eintrag_id}", headers=auth_headers(token))
    assert delete.status_code == 204

    liste = await client.get(
        "/api/zeiterfassung", headers=auth_headers(token), params={"techniker_id": str(techniker.id)}
    )
    assert liste.json() == []


@pytest.mark.asyncio
async def test_fremder_kann_eintrag_nicht_bearbeiten_oder_loeschen(client, make_mandant, make_user):
    mandant = await make_mandant()
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token1 = await login(client, tech1.email, "pw-123456")
    token2 = await login(client, tech2.email, "pw-123456")

    start = datetime.now(timezone.utc)
    create = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token1),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "krankheit",
        },
    )
    eintrag_id = create.json()["id"]

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}", headers=auth_headers(token2), json={"taetigkeit": "x"}
    )
    assert patch.status_code == 404

    delete = await client.delete(f"/api/zeiterfassung/{eintrag_id}", headers=auth_headers(token2))
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_eintrag_bleibt_ohne_zeitliche_beschraenkung_bearbeitbar(client, make_mandant, make_user):
    """Keine Drittbestaetigung mehr noetig -- ein Eintrag bleibt fuer den
    Ersteller dauerhaft aenderbar/loeschbar (solange er nicht laeuft)."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) - timedelta(days=30)
    create = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "schulung",
        },
    )
    eintrag_id = create.json()["id"]

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"taetigkeit": "auch spaeter noch aenderbar"},
    )
    assert patch.status_code == 200

    delete = await client.delete(f"/api/zeiterfassung/{eintrag_id}", headers=auth_headers(token))
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_freigeben_endpoint_existiert_nicht_mehr(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        "/api/zeiterfassung/00000000-0000-0000-0000-000000000000/freigeben",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_sieht_alle_eintraege_mandantweit_ohne_techniker_filter(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    tech1_token = await login(client, tech1.email, "pw-123456")
    tech2_token = await login(client, tech2.email, "pw-123456")

    start = datetime.now(timezone.utc)
    for token in (tech1_token, tech2_token):
        await client.post(
            "/api/zeiterfassung/manuell",
            headers=auth_headers(token),
            json={
                "start_at": start.isoformat(),
                "ende_at": (start + timedelta(hours=1)).isoformat(),
                "kategorie": "sonstiges",
            },
        )

    resp = await client.get("/api/zeiterfassung", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    techniker_ids = {e["techniker_id"] for e in resp.json()}
    assert techniker_ids == {str(tech1.id), str(tech2.id)}


@pytest.mark.asyncio
async def test_pause_urlaub_krankheit_zaehlen_nicht_in_stunden_summe(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    # Anker deutlich in der Vergangenheit (unabhaengig von der Tageszeit des
    # Testlaufs): der Start darf laut Validierung nicht in der Zukunft
    # liegen, ein fester "heute 8 Uhr"-Anker waere je nach Uhrzeit selbst
    # schon in der Zukunft.
    anker = datetime.now(timezone.utc) - timedelta(hours=20)
    for kategorie, start_offset, dauer_stunden in (
        ("urlaub", 0, 8),
        ("pause", 9, 0.5),
        ("krankheit", 10, 1),
        ("verwaltung", 12, 2),
    ):
        start = anker + timedelta(hours=start_offset)
        await client.post(
            "/api/zeiterfassung/manuell",
            headers=auth_headers(token),
            json={
                "start_at": start.isoformat(),
                "ende_at": (start + timedelta(hours=dauer_stunden)).isoformat(),
                "kategorie": kategorie,
            },
        )

    resp = await client.get("/api/zeiterfassung/statistik", headers=auth_headers(token))
    assert resp.status_code == 200
    # Nur die 2 Stunden "verwaltung" zaehlen als Arbeitszeit.
    assert resp.json()["wochenstunden"] == "2.0"


@pytest.mark.asyncio
async def test_start_in_der_zukunft_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "sonstiges",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ende_in_naher_zukunft_bei_start_jetzt_ist_erlaubt(client, make_mandant, make_user):
    """Ganztaegiger Eintrag 'ab jetzt' -- das Ende liegt legitim in der
    Zukunft, nur der Start darf nicht in der Zukunft liegen."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=8)).isoformat(),
            "kategorie": "urlaub",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_laufender_timer_nur_taetigkeit_per_patch_aenderbar(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    start_resp = await client.post(
        "/api/zeiterfassung/start",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id)},
    )
    assert start_resp.status_code == 201
    eintrag_id = start_resp.json()["id"]

    # Taetigkeit darf auch bei laufendem Timer nachgetragen werden.
    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"taetigkeit": "Wartung an Anlage"},
    )
    assert patch.status_code == 200
    assert patch.json()["taetigkeit"] == "Wartung an Anlage"
    assert patch.json()["ende_at"] is None

    # Andere Felder (z.B. start_at) sind bei laufendem Timer weiterhin
    # gesperrt -- ein Timer wird ausschliesslich ueber "stop" beendet.
    patch_start = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"start_at": datetime.now(timezone.utc).isoformat()},
    )
    assert patch_start.status_code == 409


@pytest.mark.asyncio
async def test_manueller_eintrag_bei_abgerechnetem_vorgang_gesperrt(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="abgerechnet")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) - timedelta(hours=1)
    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(minutes=30)).isoformat(),
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang.id),
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bearbeiten_und_loeschen_bei_stornierten_vorgang_gesperrt(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) - timedelta(hours=1)
    create = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(minutes=30)).isoformat(),
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang.id),
        },
    )
    assert create.status_code == 201
    eintrag_id = create.json()["id"]

    async with system_session() as session:
        db_vorgang = await session.get(Vorgang, vorgang.id)
        db_vorgang.status = "storniert"
        await session.flush()

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"taetigkeit": "nachtraeglich"},
    )
    assert patch.status_code == 409

    delete = await client.delete(f"/api/zeiterfassung/{eintrag_id}", headers=auth_headers(token))
    assert delete.status_code == 409


@pytest.mark.asyncio
async def test_eintrag_ohne_vorgang_bleibt_bearbeitbar_trotz_gesperrtem_vorgang_anderswo(
    client, make_mandant, make_user
):
    """Die Sperre haengt am verknuepften Vorgang -- ein Eintrag ganz ohne
    Vorgangsbezug (z.B. Urlaub) ist davon nie betroffen."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) - timedelta(hours=2)
    create = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(hours=1)).isoformat(),
            "kategorie": "urlaub",
        },
    )
    eintrag_id = create.json()["id"]

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag_id}",
        headers=auth_headers(token),
        json={"taetigkeit": "Urlaubstag"},
    )
    assert patch.status_code == 200
