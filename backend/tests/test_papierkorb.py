import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_loesch_operativ_hat_schreibrechte_wie_mandant_admin(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    # loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
    # app/api/deps.py:require_roles()) und darf zusaetzlich loeschen/
    # wiederherstellen/endgueltig loeschen.
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    vorgang_resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Sollte gehen",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert vorgang_resp.status_code == 201

    vertrag_resp = await client.post(
        "/api/vertraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Sollte gehen",
            "abrechnungsart": "wartungsvertrag",
        },
    )
    assert vertrag_resp.status_code == 201

    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    mangel_resp = await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang.id),
            "beschreibung": "Sollte gehen",
            "schweregrad": "mittel",
        },
    )
    assert mangel_resp.status_code == 201


@pytest.mark.asyncio
async def test_loesch_operativ_cannot_create_or_promote_into_papierkorb_role(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")
    mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter")

    for rolle in ("loesch_ansicht", "loesch_operativ", "super_admin"):
        resp = await client.post(
            "/api/users",
            headers=auth_headers(token),
            json={
                "mandant_id": None if rolle == "super_admin" else str(mandant.id),
                "email": f"{rolle}-neu@example.de",
                "password": "pw-123456",
                "role": rolle,
                "name": "Sollte nicht gehen",
            },
        )
        assert resp.status_code == 403

    resp = await client.patch(
        f"/api/users/{mitarbeiter.id}",
        headers=auth_headers(token),
        json={"role": "loesch_operativ"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_admin_cannot_create_papierkorb_accounts(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    for rolle in ("loesch_ansicht", "loesch_operativ"):
        resp = await client.post(
            "/api/users",
            headers=auth_headers(token),
            json={
                "mandant_id": str(mandant.id),
                "email": f"{rolle}@example.de",
                "password": "pw-123456",
                "role": rolle,
                "name": "Papierkorb-User",
            },
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_admin_cannot_promote_user_into_papierkorb_role(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter")

    resp = await client.patch(
        f"/api/users/{mitarbeiter.id}",
        headers=auth_headers(token),
        json={"role": "loesch_operativ"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_create_papierkorb_accounts(client, make_mandant, make_user):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "loeschen@example.de",
            "password": "pw-123456",
            "role": "loesch_operativ",
            "name": "Loesch Operativ",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_hoechstens_ein_aktiver_loesch_operativ_pro_mandant(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")
    await make_user(mandant=mandant, role="loesch_operativ", email="erster@example.de")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "zweiter@example.de",
            "password": "pw-123456",
            "role": "loesch_operativ",
            "name": "Zweiter Loesch Operativ",
        },
    )
    assert resp.status_code == 409

    # Ein zweiter Mandant darf trotzdem einen eigenen loesch_operativ haben.
    anderer_mandant = await make_mandant(name="Anderer Betrieb")
    resp2 = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(anderer_mandant.id),
            "email": "dritter@example.de",
            "password": "pw-123456",
            "role": "loesch_operativ",
            "name": "Dritter Loesch Operativ",
        },
    )
    assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_soft_delete_kaskadiert_und_versteckt_datensaetze(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage.id)

    del_resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert del_resp.status_code == 204

    # Kunde ist ueberall (Liste + Detail) verschwunden.
    get_resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert get_resp.status_code == 404
    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert all(k["id"] != str(kunde.id) for k in list_resp.json())

    # Die kaskadierten Kinder sind ebenfalls verschwunden.
    anlage_resp = await client.get(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert anlage_resp.status_code == 404
    vorgang_resp = await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    assert vorgang_resp.status_code == 404


@pytest.mark.asyncio
async def test_loesch_ansicht_sieht_nur_den_papierkorb(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(admin_token))

    ansicht = await make_user(mandant=mandant, role="loesch_ansicht", password="pw-123456")
    token = await login(client, ansicht.email, "pw-123456")

    # Normale Fach-Endpunkte bleiben gesperrt.
    kunden_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert kunden_resp.status_code == 403

    # Der Papierkorb selbst ist lesbar.
    papierkorb_resp = await client.get("/api/papierkorb", headers=auth_headers(token))
    assert papierkorb_resp.status_code == 200
    eintraege = papierkorb_resp.json()
    assert any(e["entity_typ"] == "kunde" and e["id"] == str(kunde.id) for e in eintraege)

    # Wiederherstellen/Loeschen bleibt loesch_operativ vorbehalten.
    restore_resp = await client.post(
        f"/api/papierkorb/kunde/{kunde.id}/wiederherstellen", headers=auth_headers(token)
    )
    assert restore_resp.status_code == 403
    purge_resp = await client.delete(
        f"/api/papierkorb/kunde/{kunde.id}", headers=auth_headers(token)
    )
    assert purge_resp.status_code == 403


@pytest.mark.asyncio
async def test_loesch_operativ_sieht_fachliche_daten_und_kann_wiederherstellen(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(admin_token))

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    # Sieht fachliche Daten wie ein mitarbeiter (z.B. die restlichen Kunden).
    kunden_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert kunden_resp.status_code == 200

    # Stellt den Kunden wieder her -- kaskadiert NICHT zurueck auf die Anlage.
    restore_resp = await client.post(
        f"/api/papierkorb/kunde/{kunde.id}/wiederherstellen", headers=auth_headers(token)
    )
    assert restore_resp.status_code == 204

    get_resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert get_resp.status_code == 200
    anlage_resp = await client.get(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert anlage_resp.status_code == 404

    # Anlage einzeln wiederherstellen funktioniert weiterhin.
    restore_anlage_resp = await client.post(
        f"/api/papierkorb/anlage/{anlage.id}/wiederherstellen", headers=auth_headers(token)
    )
    assert restore_anlage_resp.status_code == 204
    anlage_resp2 = await client.get(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert anlage_resp2.status_code == 200


@pytest.mark.asyncio
async def test_endgueltiges_loeschen_entfernt_datensatz_dauerhaft(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(admin_token))

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    purge_resp = await client.delete(
        f"/api/papierkorb/kunde/{kunde.id}", headers=auth_headers(token)
    )
    assert purge_resp.status_code == 204

    papierkorb_resp = await client.get("/api/papierkorb", headers=auth_headers(token))
    assert all(e["id"] != str(kunde.id) for e in papierkorb_resp.json())

    # Ein zweiter Versuch findet nichts mehr im Papierkorb.
    purge_again_resp = await client.delete(
        f"/api/papierkorb/kunde/{kunde.id}", headers=auth_headers(token)
    )
    assert purge_again_resp.status_code == 404


@pytest.mark.asyncio
async def test_kunde_mit_versendeter_rechnung_kann_nicht_endgueltig_geloescht_werden(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    # §147 AO/§257 HGB verlangt 10 Jahre Aufbewahrung fuer ausgestellte
    # Rechnungen -- das DSGVO-Loeschrecht (Art. 17 Abs. 3 lit. b) nimmt genau
    # diesen Fall ausdruecklich aus, das endgueltige Loeschen muss also
    # verweigert werden, auch wenn der ganze Kunde geloescht werden soll.
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(admin_token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id), "betrag_netto": "100.00"},
    )
    assert rechnung_resp.status_code == 201
    rechnung_id = rechnung_resp.json()["id"]
    status_resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}",
        headers=auth_headers(admin_token),
        json={"status": "versendet"},
    )
    assert status_resp.status_code == 200

    await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(admin_token))

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    purge_resp = await client.delete(
        f"/api/papierkorb/kunde/{kunde.id}", headers=auth_headers(token)
    )
    assert purge_resp.status_code == 409
    assert "Aufbewahrungspflicht" in purge_resp.json()["detail"]

    # Nichts wurde geloescht -- der Kunde ist unveraendert weiter im
    # Papierkorb (die Transaktion wurde komplett zurueckgerollt).
    papierkorb_resp = await client.get("/api/papierkorb", headers=auth_headers(token))
    assert any(e["id"] == str(kunde.id) for e in papierkorb_resp.json())


@pytest.mark.asyncio
async def test_reine_entwurfsrechnung_kann_endgueltig_geloescht_werden(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    # Eine Rechnung im Entwurf ist noch kein tatsaechlich ausgestellter Beleg
    # -- fuer sie greift keine Aufbewahrungspflicht, das Loeschen bleibt
    # moeglich. Direkt (nicht ueber eine Kunde-Kaskade) geloescht, damit der
    # Test ausschliesslich die GoBD-Sperre prueft.
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(admin_token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id), "betrag_netto": "100.00"},
    )
    assert rechnung_resp.status_code == 201
    rechnung_id = rechnung_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(admin_token)
    )
    assert del_resp.status_code == 204

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    purge_resp = await client.delete(
        f"/api/papierkorb/rechnung/{rechnung_id}", headers=auth_headers(token)
    )
    assert purge_resp.status_code == 204


@pytest.mark.asyncio
async def test_eingangsrechnung_kann_nie_endgueltig_geloescht_werden(
    client, make_mandant, make_user
):
    # Eine Eingangsrechnung repraesentiert immer einen tatsaechlich
    # erhaltenen Beleg (kein "Entwurf"-Status vorgesehen) -- unterliegt daher
    # immer der Aufbewahrungspflicht.
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")

    er_resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(admin_token),
        json={
            "lieferant_name": "Test-Lieferant",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-01-01",
            "betrag_netto": "50.00",
        },
    )
    assert er_resp.status_code == 201
    er_id = er_resp.json()["id"]

    await client.delete(f"/api/eingangsrechnungen/{er_id}", headers=auth_headers(admin_token))

    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    token = await login(client, operativ.email, "pw-123456")

    purge_resp = await client.delete(
        f"/api/papierkorb/eingangsrechnung/{er_id}", headers=auth_headers(token)
    )
    assert purge_resp.status_code == 409
    assert "Aufbewahrungspflicht" in purge_resp.json()["detail"]
