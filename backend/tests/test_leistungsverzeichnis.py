from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.leistungsverzeichnis import LeistungsverzeichnisPosition
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login


async def _make_lv_position(mandant, kunde, **kwargs) -> LeistungsverzeichnisPosition:
    async with system_session() as session:
        position = LeistungsverzeichnisPosition(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            bezeichnung=kwargs.pop("bezeichnung", "Stundensatz Monteur"),
            einheit=kwargs.pop("einheit", "Std"),
            einzelpreis=kwargs.pop("einzelpreis", Decimal("65.00")),
            ist_stundensatz=kwargs.pop("ist_stundensatz", True),
            **kwargs,
        )
        session.add(position)
        await session.flush()
        await session.refresh(position)
        return position


@pytest.mark.asyncio
async def test_admin_kann_lv_position_anlegen_und_listen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Stundensatz Monteur",
            "einheit": "Std",
            "einzelpreis": "65.00",
            "ist_stundensatz": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bezeichnung"] == "Stundensatz Monteur"
    assert body["ist_stundensatz"] is True

    liste = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"kunde_id": str(kunde.id)}
    )
    assert liste.status_code == 200
    assert len(liste.json()) == 1

    nur_stundensaetze = await client.get(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        params={"kunde_id": str(kunde.id), "nur_stundensaetze": "true"},
    )
    assert len(nur_stundensaetze.json()) == 1


@pytest.mark.asyncio
async def test_techniker_kann_lv_position_nicht_anlegen_oder_loeschen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    position = await _make_lv_position(mandant, kunde)
    token = await login(client, techniker.email, "pw-123456")

    create_resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Pauschale"},
    )
    assert create_resp.status_code == 403

    delete_resp = await client.delete(
        f"/api/leistungsverzeichnis/{position.id}", headers=auth_headers(token)
    )
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_lv_position_ueber_mandantengrenze_nicht_sichtbar(
    client, make_mandant, make_user, make_kunde
):
    mandant_a = await make_mandant(name="Betrieb A")
    mandant_b = await make_mandant(name="Betrieb B")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a)
    position_a = await _make_lv_position(mandant_a, kunde_a)
    token_b = await login(client, admin_b.email, "pw-123456")

    resp = await client.patch(
        f"/api/leistungsverzeichnis/{position_a.id}",
        headers=auth_headers(token_b),
        json={"bezeichnung": "Uebernommen"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lv_verwendung_erstellt_verwendung_und_event(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    position = await _make_lv_position(mandant, kunde, bezeichnung="Anfahrtspauschale", ist_stundensatz=False)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/leistungsverzeichnis/{position.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "menge": "1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lv_position_id"] == str(position.id)
    assert body["menge"] == "1.00"

    async with system_session() as session:
        events = (
            await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))
        ).scalars().all()
        leistungs_events = [e for e in events if e.event_type == "leistung"]
        assert len(leistungs_events) == 1
        assert "Anfahrtspauschale" in leistungs_events[0].body

    liste_resp = await client.get(
        f"/api/leistungsverzeichnis/verwendungen?vorgang_id={vorgang.id}", headers=auth_headers(token)
    )
    assert liste_resp.status_code == 200
    liste = liste_resp.json()
    assert len(liste) == 1
    assert liste[0]["lv_bezeichnung"] == "Anfahrtspauschale"
    assert liste[0]["menge"] == "1.00"

    verwendung_id = liste[0]["id"]
    delete_resp = await client.delete(
        f"/api/leistungsverzeichnis/verwendungen/{verwendung_id}", headers=auth_headers(token)
    )
    assert delete_resp.status_code == 204

    liste_nach_delete = await client.get(
        f"/api/leistungsverzeichnis/verwendungen?vorgang_id={vorgang.id}", headers=auth_headers(token)
    )
    assert liste_nach_delete.json() == []


@pytest.mark.asyncio
async def test_lv_verwendung_entfernen_unbekannte_id_404(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(
        "/api/leistungsverzeichnis/verwendungen/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lv_verwendung_lehnt_fremden_kunden_ab(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    vorgang_b = await make_vorgang(mandant=mandant, kunde=kunde_b)
    position_a = await _make_lv_position(mandant, kunde_a)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/leistungsverzeichnis/{position_a.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang_b.id), "menge": "1"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zeiterfassung_manuell_mit_svs_kopplung(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    svs = await _make_lv_position(mandant, kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": "2026-08-10T08:00:00Z",
            "ende_at": "2026-08-10T10:00:00Z",
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang.id),
            "abrechenbar": True,
            "lv_position_id": str(svs.id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["lv_position_id"] == str(svs.id)


@pytest.mark.asyncio
async def test_zeiterfassung_lehnt_svs_fremden_kunden_ab(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    vorgang_b = await make_vorgang(mandant=mandant, kunde=kunde_b)
    svs_a = await _make_lv_position(mandant, kunde_a)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": "2026-08-10T08:00:00Z",
            "ende_at": "2026-08-10T10:00:00Z",
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang_b.id),
            "abrechenbar": True,
            "lv_position_id": str(svs_a.id),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_lv_position_mandantenweit_ohne_kunde(client, make_mandant, make_user, make_kunde):
    """kunde_id=None -- gilt fuer alle Kunden. Beim Listen mit kunde_id
    erscheinen mandantenweite UND kundenspezifische Eintraege gemeinsam,
    ohne kunde_id nur die mandantenweiten."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    allgemein = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={"bezeichnung": "Installation Wallbox"},
    )
    assert allgemein.status_code == 201
    assert allgemein.json()["kunde_id"] is None

    await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Sonderkondition Kunde"},
    )

    ohne_kunde = await client.get("/api/leistungsverzeichnis", headers=auth_headers(token))
    assert [p["bezeichnung"] for p in ohne_kunde.json()] == ["Installation Wallbox"]

    mit_kunde = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"kunde_id": str(kunde.id)}
    )
    assert {p["bezeichnung"] for p in mit_kunde.json()} == {"Installation Wallbox", "Sonderkondition Kunde"}


@pytest.mark.asyncio
async def test_lv_kalkulation_unterpunkt_lohn_und_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    hauptpunkt = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"bezeichnung": "Installation Wallbox"},
        )
    ).json()

    unterpunkt = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": hauptpunkt["id"],
            "bezeichnung": "Liefern und Montieren",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 90,
            "lohn_stundensatz": "65.00",
            "material_posten": [{"bezeichnung": "Wallbox", "menge": "1", "einzelpreis": "450.00"}],
            "material_aufschlag_prozent": "10",
        },
    )
    assert unterpunkt.status_code == 201
    up = unterpunkt.json()
    assert up["kunde_id"] is None  # vom Hauptpunkt geerbt
    assert up["lohn_gesamt"] == "97.50"
    assert up["material_gesamt"] == "495.00"
    assert up["einzelpreis"] == "592.50"

    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt["id"])
        assert haupt_db.lohn_gesamt == Decimal("97.50")
        assert haupt_db.material_gesamt == Decimal("495.00")
        assert haupt_db.einzelpreis == Decimal("592.50")


@pytest.mark.asyncio
async def test_hauptpunkt_preis_ist_summe_der_unterpunkte(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    hauptpunkt = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"bezeichnung": "Installation Wallbox"},
        )
    ).json()

    await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": hauptpunkt["id"],
            "bezeichnung": "Liefern und Montieren",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 60,
            "lohn_stundensatz": "60.00",
            "material_posten": [{"bezeichnung": "Wallbox", "menge": "1", "einzelpreis": "400.00"}],
        },
    )
    zweiter = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": hauptpunkt["id"],
            "bezeichnung": "Prüfung",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 30,
            "lohn_stundensatz": "60.00",
        },
    )
    assert zweiter.status_code == 201

    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt["id"])
        assert haupt_db.lohn_gesamt == Decimal("90.00")
        assert haupt_db.material_gesamt == Decimal("400.00")
        assert haupt_db.einzelpreis == Decimal("490.00")

    kinder = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"eltern_position_id": hauptpunkt["id"]}
    )
    assert len(kinder.json()) == 2

    # Loeschen eines Unterpunkts berechnet den Hauptpunkt neu.
    await client.delete(f"/api/leistungsverzeichnis/{zweiter.json()['id']}", headers=auth_headers(token))
    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt["id"])
        assert haupt_db.lohn_gesamt == Decimal("60.00")
        assert haupt_db.einzelpreis == Decimal("460.00")


@pytest.mark.asyncio
async def test_unterpunkt_kann_nicht_verschachtelt_werden(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    hauptpunkt = (
        await client.post(
            "/api/leistungsverzeichnis", headers=auth_headers(token), json={"bezeichnung": "Hauptpunkt"}
        )
    ).json()
    unterpunkt = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"eltern_position_id": hauptpunkt["id"], "bezeichnung": "Unterpunkt"},
        )
    ).json()

    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={"eltern_position_id": unterpunkt["id"], "bezeichnung": "Zu tief"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_lv_material_posten_mit_unbekanntem_material_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "bezeichnung": "Mit Fantasie-Material",
            "kalkulationsmodus": "berechnet",
            "material_posten": [
                {
                    "bezeichnung": "X",
                    "menge": "1",
                    "einzelpreis": "1",
                    "material_id": "00000000-0000-0000-0000-000000000000",
                }
            ],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_lv_festpreis_bleibt_frei_editierbar(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    position = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"bezeichnung": "Anfahrtspauschale", "einzelpreis": "35.00"},
        )
    ).json()
    assert position["kalkulationsmodus"] == "festpreis"
    assert position["einzelpreis"] == "35.00"

    geaendert = await client.patch(
        f"/api/leistungsverzeichnis/{position['id']}",
        headers=auth_headers(token),
        json={"einzelpreis": "40.00"},
    )
    assert geaendert.json()["einzelpreis"] == "40.00"
