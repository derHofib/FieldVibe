from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.material import Material, MaterialBestand, MaterialBewegung
from app.models.material_bedarf import MaterialBedarf
from tests.conftest import auth_headers, login


async def _make_material(mandant, **kwargs) -> Material:
    async with system_session() as session:
        material = Material(
            mandant_id=mandant.id,
            bezeichnung=kwargs.pop("bezeichnung", "Kabel NYM 3x1.5"),
            einheit=kwargs.pop("einheit", "m"),
            einzelpreis=kwargs.pop("einzelpreis", Decimal("2.50")),
            **kwargs,
        )
        session.add(material)
        await session.flush()
        await session.refresh(material)
        return material


@pytest.mark.asyncio
async def test_admin_can_create_and_list_lieferanten(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/lieferanten",
        headers=auth_headers(token),
        json={"name": "Elektro-Großhandel Müller", "email": "bestellung@mueller.de"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Elektro-Großhandel Müller"

    list_resp = await client.get("/api/lieferanten", headers=auth_headers(token))
    assert [l["name"] for l in list_resp.json()] == ["Elektro-Großhandel Müller"]


@pytest.mark.asyncio
async def test_techniker_cannot_create_lieferant(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/lieferanten", headers=auth_headers(token), json={"name": "Fremdfirma"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_isolation_for_lieferanten(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.post("/api/lieferanten", headers=auth_headers(token1), json={"name": "Nur Betrieb1"})

    list_resp = await client.get("/api/lieferanten", headers=auth_headers(token2))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_material_kann_mit_lieferant_angelegt_werden(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    lieferant_resp = await client.post(
        "/api/lieferanten", headers=auth_headers(token), json={"name": "Sonepar"}
    )
    lieferant_id = lieferant_resp.json()["id"]

    resp = await client.post(
        "/api/material",
        headers=auth_headers(token),
        json={"bezeichnung": "LS-Schalter", "lieferant_id": lieferant_id},
    )
    assert resp.status_code == 201
    assert resp.json()["lieferant_id"] == lieferant_id


@pytest.mark.asyncio
async def test_techniker_can_create_material_bedarf_and_event_emitted(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    material = await _make_material(mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "25"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["zweck"] == "bestellung"
    assert body["status"] == "offen"

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    material_events = [e for e in events_resp.json() if e["event_type"] == "material"]
    assert len(material_events) == 1
    assert "zur Bestellung vorgemerkt" in material_events[0]["body"]


@pytest.mark.asyncio
async def test_material_bedarf_rejected_when_vorgang_geschlossen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "5"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_material_bedarfe_mit_details_and_filter(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Kunde ABC")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant, bezeichnung="Sicherungsautomat")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "3", "zweck": "angebot"},
    )

    resp = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"zweck": "angebot"}
    )
    assert resp.status_code == 200
    [eintrag] = resp.json()
    assert eintrag["material_bezeichnung"] == "Sicherungsautomat"
    assert eintrag["vorgang_vorgangsnummer"] == vorgang.vorgangsnummer
    assert eintrag["kunde_name"] == "Kunde ABC"

    leer_resp = await client.get(
        "/api/material-bedarfe", headers=auth_headers(token), params={"zweck": "bestellung"}
    )
    assert leer_resp.json() == []


@pytest.mark.asyncio
async def test_delete_material_bedarf_nur_wenn_offen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "3"},
    )
    bedarf_id = created.json()["id"]

    bestellt = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf_id]},
    )
    assert bestellt.status_code == 201

    resp = await client.delete(f"/api/material-bedarfe/{bedarf_id}", headers=auth_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bestellung_from_bedarfe_gruppiert_gleiches_material_und_markiert_bestellt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="Baustelle A")
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="Baustelle B")
    material = await _make_material(mandant, bezeichnung="Kabel NYM 3x1.5", einzelpreis=Decimal("2.00"))
    lieferant_resp_token = await login(client, admin.email, "pw-123456")
    lieferant = await client.post(
        "/api/lieferanten", headers=auth_headers(lieferant_resp_token), json={"name": "Sonepar"}
    )
    lieferant_id = lieferant.json()["id"]

    bedarf1 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(lieferant_resp_token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang1.id), "menge": "10"},
    )
    bedarf2 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(lieferant_resp_token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang2.id), "menge": "15"},
    )

    resp = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(lieferant_resp_token),
        json={
            "material_bedarf_ids": [bedarf1.json()["id"], bedarf2.json()["id"]],
            "lieferant_id": lieferant_id,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "entwurf"
    assert body["lieferant_id"] == lieferant_id
    assert body["bestellnummer"].startswith("B-")
    [position] = body["positionen"]
    assert position["menge"] == "25.00"
    assert position["beschreibung"] == "Kabel NYM 3x1.5"

    async with system_session() as session:
        b1 = await session.get(MaterialBedarf, bedarf1.json()["id"])
        b2 = await session.get(MaterialBedarf, bedarf2.json()["id"])
        assert b1.status == "bestellt"
        assert b2.status == "bestellt"
        assert b1.bestellung_id == b2.bestellung_id

    events1 = await client.get(f"/api/vorgaenge/{vorgang1.id}/events", headers=auth_headers(lieferant_resp_token))
    events2 = await client.get(f"/api/vorgaenge/{vorgang2.id}/events", headers=auth_headers(lieferant_resp_token))
    assert any(e["event_type"] == "material" for e in events1.json())
    assert any(e["event_type"] == "material" for e in events2.json())


@pytest.mark.asyncio
async def test_bestellung_from_bedarfe_lehnt_bereits_bestellten_bedarf_ab(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "3"},
    )
    bedarf_id = bedarf.json()["id"]

    erste = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf_id]},
    )
    assert erste.status_code == 201

    zweite = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf_id]},
    )
    assert zweite.status_code == 400


@pytest.mark.asyncio
async def test_bestellung_from_bedarfe_lehnt_angebots_bedarf_ab(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="planung")
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={
            "material_id": str(material.id),
            "vorgang_id": str(vorgang.id),
            "menge": "3",
            "zweck": "angebot",
        },
    )

    resp = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bestellung_status_eingegangen_bucht_wareneingang_und_markiert_bedarfe_erhalten(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "8"},
    )
    created = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    bestellung_id = created.json()["id"]

    resp = await client.patch(
        f"/api/bestellungen/{bestellung_id}", headers=auth_headers(token), json={"status": "eingegangen"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "eingegangen"

    async with system_session() as session:
        bestand = (
            await session.execute(
                select(MaterialBestand).where(MaterialBestand.material_id == material.id)
            )
        ).scalar_one()
        assert bestand.menge == Decimal("8.00")

        bewegung = (
            await session.execute(
                select(MaterialBewegung).where(
                    MaterialBewegung.material_id == material.id, MaterialBewegung.typ == "eingang"
                )
            )
        ).scalar_one()
        assert bewegung.menge == Decimal("8.00")

        refreshed_bedarf = await session.get(MaterialBedarf, bedarf.json()["id"])
        assert refreshed_bedarf.status == "erhalten"


@pytest.mark.asyncio
async def test_bestellung_wareneingang_mit_korrigiertem_preis_aktualisiert_position(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant, einzelpreis=Decimal("2.50"))
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "8"},
    )
    created = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    bestellung_id = created.json()["id"]
    position_id = created.json()["positionen"][0]["id"]
    assert created.json()["positionen"][0]["einzelpreis"] == "2.50"

    resp = await client.patch(
        f"/api/bestellungen/{bestellung_id}",
        headers=auth_headers(token),
        json={"status": "eingegangen", "positionen_preise": {position_id: "1.99"}},
    )
    assert resp.status_code == 200
    assert resp.json()["positionen"][0]["einzelpreis"] == "1.99"

    reread = await client.get(f"/api/bestellungen/{bestellung_id}", headers=auth_headers(token))
    assert reread.json()["positionen"][0]["einzelpreis"] == "1.99"


@pytest.mark.asyncio
async def test_bestellung_positionen_preise_ohne_wareneingang_wird_abgelehnt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "3"},
    )
    created = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    bestellung_id = created.json()["id"]
    position_id = created.json()["positionen"][0]["id"]

    resp = await client.patch(
        f"/api/bestellungen/{bestellung_id}",
        headers=auth_headers(token),
        json={"status": "bestellt", "positionen_preise": {position_id: "1.99"}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bestellung_ungueltiger_statuswechsel_wird_abgelehnt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "2"},
    )
    created = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    bestellung_id = created.json()["id"]

    await client.patch(
        f"/api/bestellungen/{bestellung_id}", headers=auth_headers(token), json={"status": "eingegangen"}
    )

    resp = await client.patch(
        f"/api/bestellungen/{bestellung_id}", headers=auth_headers(token), json={"status": "bestellt"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bestellung_csv_und_pdf_export(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang.id), "menge": "4"},
    )
    created = await client.post(
        "/api/bestellungen/from-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf.json()["id"]]},
    )
    bestellung_id = created.json()["id"]

    csv_resp = await client.get(f"/api/bestellungen/{bestellung_id}/csv", headers=auth_headers(token))
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")

    pdf_resp = await client.get(f"/api/bestellungen/{bestellung_id}/pdf", headers=auth_headers(token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_angebot_from_material_bedarfe_gruppiert_und_markiert_in_angebot(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="beratung")
    material = await _make_material(mandant, bezeichnung="Wallbox 11kW", einzelpreis=Decimal("650.00"))
    token = await login(client, admin.email, "pw-123456")

    bedarf1 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={
            "material_id": str(material.id),
            "vorgang_id": str(vorgang.id),
            "menge": "1",
            "zweck": "angebot",
        },
    )
    bedarf2 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={
            "material_id": str(material.id),
            "vorgang_id": str(vorgang.id),
            "menge": "1",
            "zweck": "angebot",
        },
    )

    resp = await client.post(
        "/api/angebote/from-material-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf1.json()["id"], bedarf2.json()["id"]]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["vorgang_id"] == str(vorgang.id)
    assert body["kunde_id"] == str(kunde.id)
    [position] = body["positionen"]
    assert position["menge"] == "2.00"
    assert position["einzelpreis"] == "650.00"
    assert position["beschreibung"] == "Wallbox 11kW"

    async with system_session() as session:
        b1 = await session.get(MaterialBedarf, bedarf1.json()["id"])
        b2 = await session.get(MaterialBedarf, bedarf2.json()["id"])
        assert b1.status == "in_angebot"
        assert b1.angebot_id == b2.angebot_id


@pytest.mark.asyncio
async def test_angebot_from_material_bedarfe_lehnt_unterschiedliche_kunden_ab(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde1, leistungstyp="planung")
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde2, leistungstyp="planung")
    material = await _make_material(mandant)
    token = await login(client, admin.email, "pw-123456")

    bedarf1 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang1.id), "menge": "1", "zweck": "angebot"},
    )
    bedarf2 = await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token),
        json={"material_id": str(material.id), "vorgang_id": str(vorgang2.id), "menge": "1", "zweck": "angebot"},
    )

    resp = await client.post(
        "/api/angebote/from-material-bedarfe",
        headers=auth_headers(token),
        json={"material_bedarf_ids": [bedarf1.json()["id"], bedarf2.json()["id"]]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_mandant_isolation_for_material_bedarfe_und_bestellungen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    vorgang1 = await make_vorgang(mandant=mandant1, kunde=kunde1)
    material1 = await _make_material(mandant1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.post(
        "/api/material-bedarfe",
        headers=auth_headers(token1),
        json={"material_id": str(material1.id), "vorgang_id": str(vorgang1.id), "menge": "1"},
    )

    bedarfe_resp = await client.get("/api/material-bedarfe", headers=auth_headers(token2))
    assert bedarfe_resp.json() == []

    bestellungen_resp = await client.get("/api/bestellungen", headers=auth_headers(token2))
    assert bestellungen_resp.json() == []
