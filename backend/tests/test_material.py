from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.material import Material, MaterialBestand
from tests.conftest import auth_headers, login


async def _zentrallager(mandant) -> Anlage:
    async with system_session() as session:
        result = await session.execute(
            select(Anlage).where(Anlage.mandant_id == mandant.id, Anlage.objekttyp == "lager")
        )
        return result.scalars().one()


async def _make_material(mandant, *, lager: Anlage | None = None, bestand: Decimal | None = None, **kwargs) -> Material:
    async with system_session() as session:
        material = Material(
            mandant_id=mandant.id,
            bezeichnung=kwargs.pop("bezeichnung", "Kabel NYM 3x1.5"),
            einheit=kwargs.pop("einheit", "m"),
            mindestbestand=kwargs.pop("mindestbestand", Decimal("5")),
            **kwargs,
        )
        session.add(material)
        await session.flush()

        ziel_lager = lager or await _zentrallager(mandant)
        session.add(
            MaterialBestand(
                mandant_id=mandant.id,
                material_id=material.id,
                lager_id=ziel_lager.id,
                menge=Decimal("10") if bestand is None else bestand,
            )
        )
        await session.flush()
        await session.refresh(material)
        return material


@pytest.mark.asyncio
async def test_admin_can_create_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/material",
        headers=auth_headers(token),
        json={"bezeichnung": "Sicherung 16A", "einheit": "Stk", "menge": "20", "mindestbestand": "5"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bezeichnung"] == "Sicherung 16A"
    assert body["bestand_gesamt"] == "20.00"
    assert len(body["bestaende"]) == 1
    assert body["bestaende"][0]["lager_bezeichnung"] == "Zentrallager"
    assert body["bestaende"][0]["menge"] == "20.00"


@pytest.mark.asyncio
async def test_material_ohne_menge_landet_mit_null_bestand_im_zentrallager(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/material", headers=auth_headers(token), json={"bezeichnung": "Draht"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bestand_gesamt"] == "0.00"
    assert body["bestaende"][0]["lager_bezeichnung"] == "Zentrallager"


@pytest.mark.asyncio
async def test_techniker_cannot_create_or_update_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    material = await _make_material(mandant)
    token = await login(client, techniker.email, "pw-123456")

    create_resp = await client.post(
        "/api/material", headers=auth_headers(token), json={"bezeichnung": "Draht"}
    )
    assert create_resp.status_code == 403

    update_resp = await client.patch(
        f"/api/material/{material.id}", headers=auth_headers(token), json={"mindestbestand": "1"}
    )
    assert update_resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_can_record_verwendung_and_stock_decrements(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    material = await _make_material(mandant, bestand=Decimal("10"))
    lager = await _zentrallager(mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "lager_id": str(lager.id), "menge": "3"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["menge"] == "3.00"
    assert body["verwendet_von"] == str(techniker.id)

    async with system_session() as session:
        bestand = (
            await session.execute(
                select(MaterialBestand).where(
                    MaterialBestand.material_id == material.id, MaterialBestand.lager_id == lager.id
                )
            )
        ).scalar_one()
        assert bestand.menge == Decimal("7")

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "material" in event_types


@pytest.mark.asyncio
async def test_verwendung_rejected_when_bestand_insufficient(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant, bestand=Decimal("2"))
    lager = await _zentrallager(mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "lager_id": str(lager.id), "menge": "5"},
    )
    assert resp.status_code == 400

    async with system_session() as session:
        bestand = (
            await session.execute(
                select(MaterialBestand).where(
                    MaterialBestand.material_id == material.id, MaterialBestand.lager_id == lager.id
                )
            )
        ).scalar_one()
        assert bestand.menge == Decimal("2")


@pytest.mark.asyncio
async def test_material_bestand_cannot_go_negative_at_db_level(make_mandant):
    mandant = await make_mandant()
    lager = await _zentrallager(mandant)

    with pytest.raises(IntegrityError):
        async with system_session() as session:
            material = Material(mandant_id=mandant.id, bezeichnung="Test")
            session.add(material)
            await session.flush()
            session.add(
                MaterialBestand(
                    mandant_id=mandant.id, material_id=material.id, lager_id=lager.id, menge=Decimal("-1")
                )
            )
            await session.flush()


@pytest.mark.asyncio
async def test_mandant_isolation_for_material(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    await _make_material(mandant1)
    token2 = await login(client, admin2.email, "pw-123456")

    list_resp = await client.get("/api/material", headers=auth_headers(token2))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_umlagerung_zwischen_zwei_lagerorten(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    zentrallager = await _zentrallager(mandant)
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    material = await _make_material(mandant, lager=zentrallager, bestand=Decimal("10"))
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/umlagern",
        headers=auth_headers(token),
        json={
            "von_lager_id": str(zentrallager.id),
            "nach_lager_id": str(fahrzeug.id),
            "menge": "4",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    bestaende_by_lager = {b["lager_id"]: b["menge"] for b in body["bestaende"]}
    assert bestaende_by_lager[str(zentrallager.id)] == "6.00"
    assert bestaende_by_lager[str(fahrzeug.id)] == "4.00"


@pytest.mark.asyncio
async def test_umlagerung_scheitert_bei_zu_wenig_bestand(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    zentrallager = await _zentrallager(mandant)
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    material = await _make_material(mandant, lager=zentrallager, bestand=Decimal("2"))
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/material/{material.id}/umlagern",
        headers=auth_headers(token),
        json={
            "von_lager_id": str(zentrallager.id),
            "nach_lager_id": str(fahrzeug.id),
            "menge": "5",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bestand_setzen_erstellt_korrektur_bewegung(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    zentrallager = await _zentrallager(mandant)
    material = await _make_material(mandant, lager=zentrallager, bestand=Decimal("10"))
    token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        f"/api/material/{material.id}/bestand/{zentrallager.id}",
        headers=auth_headers(token),
        json={"menge": "15"},
    )
    assert resp.status_code == 200
    assert resp.json()["bestand_gesamt"] == "15.00"

    bewegungen_resp = await client.get(
        f"/api/material/{material.id}/bewegungen", headers=auth_headers(token)
    )
    typen = [b["typ"] for b in bewegungen_resp.json()]
    assert "korrektur" in typen


@pytest.mark.asyncio
async def test_fahrzeug_ist_gueltiger_lagerort_fuer_neues_material(
    client, make_mandant, make_user, make_anlage
):
    """Kernidee: ein Asset vom objekttyp=fahrzeug ist sofort ein nutzbarer
    Lagerort, ohne eigenes Onboarding fuer "Lager anlegen"."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/material",
        headers=auth_headers(token),
        json={"bezeichnung": "Kabelbinder", "lager_id": str(fahrzeug.id), "menge": "50"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bestaende"][0]["lager_id"] == str(fahrzeug.id)
    assert body["bestaende"][0]["lager_bezeichnung"] == "Transporter"


@pytest.mark.asyncio
async def test_unterbestand_story_ueber_alle_lagerorte_summiert(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    zentrallager = await _zentrallager(mandant)
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    material = await _make_material(
        mandant, lager=zentrallager, bestand=Decimal("1"), mindestbestand=Decimal("5")
    )
    async with system_session() as session:
        session.add(
            MaterialBestand(
                mandant_id=mandant.id, material_id=material.id, lager_id=fahrzeug.id, menge=Decimal("1")
            )
        )
        await session.flush()
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/stories", headers=auth_headers(token))
    assert resp.status_code == 200
    material_items = [m for m in resp.json()["material"] if m["ziel_id"] == str(material.id)]
    assert len(material_items) == 1
    assert "2" in material_items[0]["subtitel"]
