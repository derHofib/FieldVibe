from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.leistungsverzeichnis import Leistungsverzeichnis, LeistungsverzeichnisKunde, LeistungsverzeichnisPosition
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login


async def _make_lv(mandant, kunde=None, **kwargs) -> Leistungsverzeichnis:
    async with system_session() as session:
        lv = Leistungsverzeichnis(mandant_id=mandant.id, name=kwargs.pop("name", "Allgemein"), **kwargs)
        session.add(lv)
        await session.flush()
        if kunde is not None:
            session.add(LeistungsverzeichnisKunde(mandant_id=mandant.id, leistungsverzeichnis_id=lv.id, kunde_id=kunde.id))
            await session.flush()
        await session.refresh(lv)
        return lv


async def _make_lv_position(mandant, lv, **kwargs) -> LeistungsverzeichnisPosition:
    async with system_session() as session:
        position = LeistungsverzeichnisPosition(
            mandant_id=mandant.id,
            leistungsverzeichnis_id=lv.id,
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
async def test_admin_kann_lv_anlegen_und_position_hinzufuegen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    lv_resp = await client.post(
        "/api/leistungsverzeichnisse",
        headers=auth_headers(token),
        json={"name": "Wartungsvertraege", "kunden_ids": [str(kunde.id)]},
    )
    assert lv_resp.status_code == 201
    lv = lv_resp.json()
    assert lv["kunden_ids"] == [str(kunde.id)]

    pos_resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "leistungsverzeichnis_id": lv["id"],
            "bezeichnung": "Stundensatz Monteur",
            "einheit": "Std",
            "einzelpreis": "65.00",
            "ist_stundensatz": True,
        },
    )
    assert pos_resp.status_code == 201
    position = pos_resp.json()
    assert position["leistungsverzeichnis_id"] == lv["id"]

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

    je_lv = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"leistungsverzeichnis_id": lv["id"]}
    )
    assert len(je_lv.json()) == 1


@pytest.mark.asyncio
async def test_position_ohne_lv_id_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/leistungsverzeichnis", headers=auth_headers(token), json={"bezeichnung": "Ohne LV"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_techniker_kann_lv_nicht_anlegen_oder_loeschen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    lv = await _make_lv(mandant, kunde)
    token = await login(client, techniker.email, "pw-123456")

    create_resp = await client.post(
        "/api/leistungsverzeichnisse", headers=auth_headers(token), json={"name": "Pauschalen"}
    )
    assert create_resp.status_code == 403

    delete_resp = await client.delete(f"/api/leistungsverzeichnisse/{lv.id}", headers=auth_headers(token))
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_lv_position_ueber_mandantengrenze_nicht_sichtbar(client, make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Betrieb A")
    mandant_b = await make_mandant(name="Betrieb B")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a)
    lv_a = await _make_lv(mandant_a, kunde_a)
    position_a = await _make_lv_position(mandant_a, lv_a)
    token_b = await login(client, admin_b.email, "pw-123456")

    resp = await client.patch(
        f"/api/leistungsverzeichnis/{position_a.id}",
        headers=auth_headers(token_b),
        json={"bezeichnung": "Uebernommen"},
    )
    assert resp.status_code == 404

    lv_resp = await client.get(f"/api/leistungsverzeichnisse/{lv_a.id}", headers=auth_headers(token_b))
    assert lv_resp.status_code == 404


@pytest.mark.asyncio
async def test_lv_verwendung_erstellt_verwendung_und_event(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    lv = await _make_lv(mandant, kunde)
    position = await _make_lv_position(mandant, lv, bezeichnung="Anfahrtspauschale", ist_stundensatz=False)
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
async def test_lv_verwendung_entfernen_unbekannte_id_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(
        "/api/leistungsverzeichnis/verwendungen/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lv_verwendung_lehnt_fremden_kunden_ab(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    vorgang_b = await make_vorgang(mandant=mandant, kunde=kunde_b)
    lv_a = await _make_lv(mandant, kunde_a)
    position_a = await _make_lv_position(mandant, lv_a)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/leistungsverzeichnis/{position_a.id}/verwendung",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang_b.id), "menge": "1"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zeiterfassung_manuell_mit_svs_kopplung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    lv = await _make_lv(mandant, kunde)
    svs = await _make_lv_position(mandant, lv)
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
async def test_zeiterfassung_lehnt_svs_fremden_kunden_ab(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    vorgang_b = await make_vorgang(mandant=mandant, kunde=kunde_b)
    lv_a = await _make_lv(mandant, kunde_a)
    svs_a = await _make_lv_position(mandant, lv_a)
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
async def test_lv_kundenfilter_zeigt_allgemeine_plus_zugewiesene(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    token = await login(client, admin.email, "pw-123456")

    lv_allgemein = await _make_lv(mandant, kunde=None, name="Allgemein")
    await _make_lv_position(mandant, lv_allgemein, bezeichnung="Allgemein")
    lv_a = await _make_lv(mandant, kunde=kunde_a, name="Nur A")
    await _make_lv_position(mandant, lv_a, bezeichnung="Nur A")

    fuer_a = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"kunde_id": str(kunde_a.id)}
    )
    assert {p["bezeichnung"] for p in fuer_a.json()} == {"Allgemein", "Nur A"}

    fuer_b = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"kunde_id": str(kunde_b.id)}
    )
    assert {p["bezeichnung"] for p in fuer_b.json()} == {"Allgemein"}


@pytest.mark.asyncio
async def test_lv_mehreren_kunden_zuweisen_und_aendern(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Kunde A")
    kunde_b = await make_kunde(mandant=mandant, name="Kunde B")
    kunde_c = await make_kunde(mandant=mandant, name="Kunde C")
    token = await login(client, admin.email, "pw-123456")

    erstellt = await client.post(
        "/api/leistungsverzeichnisse",
        headers=auth_headers(token),
        json={"name": "Mehrfach zugewiesen", "kunden_ids": [str(kunde_a.id), str(kunde_b.id)]},
    )
    assert erstellt.status_code == 201
    assert set(erstellt.json()["kunden_ids"]) == {str(kunde_a.id), str(kunde_b.id)}

    geaendert = await client.patch(
        f"/api/leistungsverzeichnisse/{erstellt.json()['id']}",
        headers=auth_headers(token),
        json={"kunden_ids": [str(kunde_c.id)]},
    )
    assert geaendert.status_code == 200
    assert geaendert.json()["kunden_ids"] == [str(kunde_c.id)]


@pytest.mark.asyncio
async def test_lv_duplizieren_kopiert_positionen_ohne_kunden(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    lv = await _make_lv(mandant, kunde=kunde, name="Original")
    hauptpunkt = await _make_lv_position(mandant, lv, bezeichnung="Hauptpunkt", ist_stundensatz=False)
    await _make_lv_position(
        mandant, lv, bezeichnung="Unterpunkt", ist_stundensatz=False, eltern_position_id=hauptpunkt.id
    )

    resp = await client.post(f"/api/leistungsverzeichnisse/{lv.id}/duplizieren", headers=auth_headers(token))
    assert resp.status_code == 201
    kopie = resp.json()
    assert kopie["name"] == "Original (Kopie)"
    # Unabhaengige Kunden-Zuweisung: die Kopie erbt sie nicht vom Original.
    assert kopie["kunden_ids"] == []

    positionen = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"leistungsverzeichnis_id": kopie["id"]}
    )
    assert len(positionen.json()) == 1
    kopierter_hauptpunkt = positionen.json()[0]
    assert kopierter_hauptpunkt["bezeichnung"] == "Hauptpunkt"

    unterpunkte = await client.get(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        params={"eltern_position_id": kopierter_hauptpunkt["id"]},
    )
    assert len(unterpunkte.json()) == 1
    assert unterpunkte.json()[0]["bezeichnung"] == "Unterpunkt"

    # Original bleibt unveraendert.
    original_positionen = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"leistungsverzeichnis_id": lv.id}
    )
    assert len(original_positionen.json()) == 1


@pytest.mark.asyncio
async def test_lv_loeschen_kaskadiert_auf_positionen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    lv = await _make_lv(mandant, name="Zu loeschen")
    position = await _make_lv_position(mandant, lv, bezeichnung="Position")

    resp = await client.delete(f"/api/leistungsverzeichnisse/{lv.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    async with system_session() as session:
        position_db = await session.get(LeistungsverzeichnisPosition, position.id)
        assert position_db.geloescht_am is not None

    liste = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"leistungsverzeichnis_id": str(lv.id)}
    )
    assert liste.json() == []


@pytest.mark.asyncio
async def test_lv_kalkulation_unterpunkt_lohn_und_material(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    lv = await _make_lv(mandant, name="LV")

    hauptpunkt = await _make_lv_position(mandant, lv, bezeichnung="Installation Wallbox", ist_stundensatz=False)

    unterpunkt = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": str(hauptpunkt.id),
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
    assert up["lohn_gesamt"] == "97.50"
    assert up["material_gesamt"] == "495.00"
    assert up["einzelpreis"] == "592.50"

    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt.id)
        assert haupt_db.lohn_gesamt == Decimal("97.50")
        assert haupt_db.material_gesamt == Decimal("495.00")
        assert haupt_db.einzelpreis == Decimal("592.50")


@pytest.mark.asyncio
async def test_hauptpunkt_summe_beruecksichtigt_festpreis_unterpunkt(client, make_mandant, make_user):
    """Regression: ein Festpreis-Unterpunkt hat kein lohn_gesamt/
    material_gesamt (bleibt dort immer 0, siehe _berechne_eigenen_preis) --
    _neu_berechnen muss trotzdem seinen tatsaechlichen einzelpreis in die
    Summe des Hauptpunkts einrechnen, statt ihn stillschweigend mit 0 EUR
    zu zaehlen."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    lv = await _make_lv(mandant, name="LV")

    hauptpunkt = await _make_lv_position(mandant, lv, bezeichnung="Installation Wallbox", ist_stundensatz=False)

    festpreis_unterpunkt = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": str(hauptpunkt.id),
            "bezeichnung": "Anfahrt",
            "einzelpreis": "15.00",
        },
    )
    assert festpreis_unterpunkt.status_code == 201
    assert festpreis_unterpunkt.json()["lohn_gesamt"] == "0.00"
    assert festpreis_unterpunkt.json()["material_gesamt"] == "0.00"

    berechnet_unterpunkt = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": str(hauptpunkt.id),
            "bezeichnung": "Montage",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 60,
            "lohn_stundensatz": "50.00",
        },
    )
    assert berechnet_unterpunkt.status_code == 201
    assert berechnet_unterpunkt.json()["einzelpreis"] == "50.00"

    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt.id)
        # 15.00 (Festpreis) + 50.00 (berechnet) -- nicht nur 50.00.
        assert haupt_db.einzelpreis == Decimal("65.00")
        assert haupt_db.lohn_gesamt == Decimal("50.00")
        assert haupt_db.material_gesamt == Decimal("0.00")


@pytest.mark.asyncio
async def test_hauptpunkt_preis_ist_summe_der_unterpunkte(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    lv = await _make_lv(mandant, name="LV")

    hauptpunkt = await _make_lv_position(mandant, lv, bezeichnung="Installation Wallbox", ist_stundensatz=False)

    await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "eltern_position_id": str(hauptpunkt.id),
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
            "eltern_position_id": str(hauptpunkt.id),
            "bezeichnung": "Prüfung",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 30,
            "lohn_stundensatz": "60.00",
        },
    )
    assert zweiter.status_code == 201

    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt.id)
        assert haupt_db.lohn_gesamt == Decimal("90.00")
        assert haupt_db.material_gesamt == Decimal("400.00")
        assert haupt_db.einzelpreis == Decimal("490.00")

    kinder = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"eltern_position_id": str(hauptpunkt.id)}
    )
    assert len(kinder.json()) == 2

    # Loeschen eines Unterpunkts berechnet den Hauptpunkt neu.
    await client.delete(f"/api/leistungsverzeichnis/{zweiter.json()['id']}", headers=auth_headers(token))
    async with system_session() as session:
        haupt_db = await session.get(LeistungsverzeichnisPosition, hauptpunkt.id)
        assert haupt_db.lohn_gesamt == Decimal("60.00")
        assert haupt_db.einzelpreis == Decimal("460.00")


@pytest.mark.asyncio
async def test_unterpunkt_kann_nicht_verschachtelt_werden(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    lv = await _make_lv(mandant, name="LV")

    hauptpunkt = await _make_lv_position(mandant, lv, bezeichnung="Hauptpunkt", ist_stundensatz=False)
    unterpunkt = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"eltern_position_id": str(hauptpunkt.id), "bezeichnung": "Unterpunkt"},
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
    lv = await _make_lv(mandant, name="LV")

    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "leistungsverzeichnis_id": str(lv.id),
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
    lv = await _make_lv(mandant, name="LV")

    position = (
        await client.post(
            "/api/leistungsverzeichnis",
            headers=auth_headers(token),
            json={"leistungsverzeichnis_id": str(lv.id), "bezeichnung": "Anfahrtspauschale", "einzelpreis": "35.00"},
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


@pytest.mark.asyncio
async def test_lv_gemeinkosten_und_gewinn_wagnis_in_preis(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    lv = await _make_lv(mandant, name="LV")

    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "leistungsverzeichnis_id": str(lv.id),
            "bezeichnung": "Mit Gemeinkosten",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 60,
            "lohn_stundensatz": "50.00",
            "lohn_gemeinkosten_prozent": "20",
            "material_posten": [{"bezeichnung": "Kabel", "menge": "1", "einzelpreis": "100.00"}],
            "material_aufschlag_prozent": "10",
            "gewinn_wagnis_prozent": "15",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # Lohn: 50 * (1+0.20) = 60, Material: 100 * (1+0.10) = 110,
    # Zwischensumme 170 * (1+0.15) = 195.50.
    assert body["lohn_gesamt"] == "69.00"
    assert body["material_gesamt"] == "126.50"
    assert body["einzelpreis"] == "195.50"


@pytest.mark.asyncio
async def test_lv_position_uebernimmt_mandant_defaults_bei_anlage(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"standard_lohn_gemeinkosten_prozent": "25", "standard_gewinn_wagnis_prozent": "5"},
    )

    lv = await _make_lv(mandant, name="LV")
    resp = await client.post(
        "/api/leistungsverzeichnis",
        headers=auth_headers(token),
        json={
            "leistungsverzeichnis_id": str(lv.id),
            "bezeichnung": "Mit Default",
            "kalkulationsmodus": "berechnet",
            "lohn_minuten": 60,
            "lohn_stundensatz": "40.00",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lohn_gemeinkosten_prozent"] == "25.00"
    assert body["gewinn_wagnis_prozent"] == "5.00"

    # Danach geaenderter Mandant-Default rechnet die bereits angelegte
    # Position NICHT rueckwirkend neu.
    await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"standard_lohn_gemeinkosten_prozent": "99"},
    )
    unveraendert = await client.get(
        "/api/leistungsverzeichnis", headers=auth_headers(token), params={"leistungsverzeichnis_id": str(lv.id)}
    )
    assert unveraendert.json()[0]["lohn_gemeinkosten_prozent"] == "25.00"
