import pytest

from app.db.session import system_session
from app.models.mangel import Mangel
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login


async def _make_mangel(mandant, vorgang, gemeldet_von, **kwargs) -> Mangel:
    async with system_session() as session:
        mangel = Mangel(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            beschreibung=kwargs.pop("beschreibung", "Testmangel"),
            gemeldet_von=gemeldet_von.id,
            **kwargs,
        )
        session.add(mangel)
        await session.flush()
        await session.refresh(mangel)
        return mangel


@pytest.mark.asyncio
async def test_create_angebot_with_positionen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/angebote",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "positionen": [
                {"beschreibung": "Installation", "menge": "2", "einheit": "Std", "einzelpreis": "80.00"},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "entwurf"
    assert body["gesamt_netto"] == "160.00"
    assert body["gesamt_brutto"] == "190.40"


@pytest.mark.asyncio
async def test_techniker_cannot_create_angebot(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/angebote", headers=auth_headers(token), json={"kunde_id": str(kunde.id)}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_angebot_from_maengel_full_workflow(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    mangel1 = await _make_mangel(mandant, vorgang, admin, beschreibung="Kabel defekt")
    mangel2 = await _make_mangel(mandant, vorgang, admin, beschreibung="Sicherung kaputt")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote/from-maengel",
        headers=auth_headers(token),
        json={"mangel_ids": [str(mangel1.id), str(mangel2.id)]},
    )
    assert created.status_code == 201
    angebot = created.json()
    assert len(angebot["positionen"]) == 2
    assert angebot["vorgang_id"] == str(vorgang.id)
    angebot_id = angebot["id"]

    # Mängel sind jetzt "in_angebot" und koennen nicht doppelt verwendet werden
    duplicate = await client.post(
        "/api/angebote/from-maengel",
        headers=auth_headers(token),
        json={"mangel_ids": [str(mangel1.id)]},
    )
    assert duplicate.status_code == 400

    # Ohne Preise versenden ist erlaubt (Preis 0 ist gueltig, nur "keine Position" wird blockiert)
    versendet = await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versendet.status_code == 200
    assert versendet.json()["versendet_am"] is not None

    angenommen = await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "angenommen"}
    )
    assert angenommen.status_code == 200
    assert angenommen.json()["angenommen_am"] is not None

    async with system_session() as session:
        m1 = await session.get(Mangel, mangel1.id)
        m2 = await session.get(Mangel, mangel2.id)
        assert m1.status == "in_bearbeitung"
        assert m2.status == "in_bearbeitung"
        assert m1.reparatur_vorgang_id is not None
        assert m1.reparatur_vorgang_id == m2.reparatur_vorgang_id

        reparatur_vorgang = await session.get(Vorgang, m1.reparatur_vorgang_id)
        assert reparatur_vorgang.leistungstyp == "stoerung"
        assert reparatur_vorgang.kunde_id == kunde.id

    # Vorgang abschliessen markiert die Maengel als behoben
    reparatur_vorgang_id = str(m1.reparatur_vorgang_id)
    resp = await client.patch(
        f"/api/vorgaenge/{reparatur_vorgang_id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen"},
    )
    assert resp.status_code == 200

    async with system_session() as session:
        m1 = await session.get(Mangel, mangel1.id)
        assert m1.status == "behoben"
        assert m1.behoben_am is not None


@pytest.mark.asyncio
async def test_angebot_rejected_reverts_maengel_to_offen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    mangel = await _make_mangel(mandant, vorgang, admin)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote/from-maengel",
        headers=auth_headers(token),
        json={"mangel_ids": [str(mangel.id)]},
    )
    angebot_id = created.json()["id"]

    await client.patch(f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "versendet"})
    resp = await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "abgelehnt"}
    )
    assert resp.status_code == 200
    assert resp.json()["abgelehnt_am"] is not None

    async with system_session() as session:
        refreshed = await session.get(Mangel, mangel.id)
        assert refreshed.status == "offen"
        assert refreshed.angebot_id is None


@pytest.mark.asyncio
async def test_invalid_status_transition_skips_versendet(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote", headers=auth_headers(token), json={"kunde_id": str(kunde.id)}
    )
    angebot_id = created.json()["id"]

    resp = await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "angenommen"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_versenden_ohne_positionen_rejected(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote", headers=auth_headers(token), json={"kunde_id": str(kunde.id)}
    )
    angebot_id = created.json()["id"]

    resp = await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_angebot_pdf_returns_pdf_bytes(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "positionen": [{"beschreibung": "Material", "einzelpreis": "42.00"}],
        },
    )
    angebot_id = created.json()["id"]

    resp = await client.get(f"/api/angebote/{angebot_id}/pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_mandant_isolation_for_angebote(client, make_mandant, make_user, make_kunde):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post(
        "/api/angebote", headers=auth_headers(token1), json={"kunde_id": str(kunde1.id)}
    )
    assert created.status_code == 201

    list_resp = await client.get("/api/angebote", headers=auth_headers(token2))
    assert list_resp.json() == []
