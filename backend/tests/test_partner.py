from datetime import date, timedelta

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.partner_nachweis import PartnerNachweis
from app.models.partner_zugang import PartnerZugang
from tests.conftest import auth_headers, login


async def _make_zugang(mandant, partner, *, email=None, password="partner-pw-123", aktiv=True, name="Partner-Nutzer"):
    async with system_session() as session:
        zugang = PartnerZugang(
            mandant_id=mandant.id,
            partner_id=partner.id,
            email=email or f"partner-{partner.id}@example.de",
            password_hash=hash_password(password),
            name=name,
            aktiv=aktiv,
        )
        session.add(zugang)
        await session.flush()
        await session.refresh(zugang)
        return zugang


async def _partner_login(client, email, password):
    resp = await client.post("/api/partnerportal/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()


# --- Interne Verwaltung -----------------------------------------------------


@pytest.mark.asyncio
async def test_mandant_admin_kann_partner_anlegen_und_lesen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/partner",
        headers=auth_headers(token),
        json={"name": "Elektro Subunternehmer KG", "gewerk": "Zählerschrank"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Elektro Subunternehmer KG"
    assert body["aktiv"] is True

    list_resp = await client.get("/api/partner", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_techniker_darf_partner_nicht_anlegen(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/partner", headers=auth_headers(token), json={"name": "Sollte nicht gehen"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_partner_ist_mandantengetrennt(client, make_mandant, make_user, make_partner):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    partner_b = await make_partner(mandant=mandant_b, name="Nur in Mandant B")
    token_a = await login(client, admin_a.email, "pw-123456")

    resp = await client.get(f"/api/partner/{partner_b.id}", headers=auth_headers(token_a))
    assert resp.status_code == 404

    list_resp = await client.get("/api/partner", headers=auth_headers(token_a))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_deaktiviertes_modul_sperrt_partner_endpoints(client, make_mandant, make_user):
    mandant = await make_mandant()
    async with system_session() as session:
        m = await session.get(Mandant, mandant.id)
        m.deaktivierte_module = ["nachunternehmer"]
        await session.flush()

    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/partner", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_freistellungsbescheinigung_nachweis_crud_und_ablauf_flag(
    client, make_mandant, make_user, make_partner
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    partner = await make_partner(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    abgelaufen = await client.post(
        f"/api/partner/{partner.id}/nachweise",
        headers=auth_headers(token),
        json={
            "typ": "freistellungsbescheinigung",
            "gueltig_bis": str(date.today() - timedelta(days=1)),
        },
    )
    assert abgelaufen.status_code == 201
    assert abgelaufen.json()["abgelaufen"] is True

    gueltig = await client.post(
        f"/api/partner/{partner.id}/nachweise",
        headers=auth_headers(token),
        json={"typ": "haftpflichtversicherung", "gueltig_bis": str(date.today() + timedelta(days=30))},
    )
    assert gueltig.status_code == 201
    assert gueltig.json()["abgelaufen"] is False


# --- Vorgang-Zuweisung -------------------------------------------------------


@pytest.mark.asyncio
async def test_partner_zuweisung_setzt_vorgeschlagen_und_warnt_ohne_freistellung(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    partner = await make_partner(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}/partner-zuweisung",
        headers=auth_headers(token),
        json={"partner_id": str(partner.id), "partner_honorar_netto": "450.00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["partner_freigabe_status"] == "vorgeschlagen"
    assert body["freistellungsbescheinigung_warnung"] is True

    vorgang_resp = await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    assert vorgang_resp.json()["partner_id"] == str(partner.id)
    assert vorgang_resp.json()["partner_honorar_netto"] == "450.00"


@pytest.mark.asyncio
async def test_partner_zuweisung_ohne_warnung_mit_gueltiger_freistellung(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    partner = await make_partner(mandant=mandant)
    async with system_session() as session:
        session.add(
            PartnerNachweis(
                mandant_id=mandant.id,
                partner_id=partner.id,
                typ="freistellungsbescheinigung",
                gueltig_bis=date.today() + timedelta(days=90),
            )
        )
        await session.flush()
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}/partner-zuweisung",
        headers=auth_headers(token),
        json={"partner_id": str(partner.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["freistellungsbescheinigung_warnung"] is False


@pytest.mark.asyncio
async def test_partner_zuweisung_aufheben(client, make_mandant, make_user, make_kunde, make_vorgang, make_partner):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}/partner-zuweisung",
        headers=auth_headers(token),
        json={"partner_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["partner_id"] is None
    assert resp.json()["partner_freigabe_status"] is None


# --- Einladung ----------------------------------------------------------------


async def _extrahiere_token(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.asyncio
async def test_partner_einladen_und_registrieren(client, make_mandant, make_user, make_partner):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    partner = await make_partner(mandant=mandant, name="Elektro Subunternehmer KG")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/partner/{partner.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "einladung@partner.example.de"},
    )
    assert resp.status_code == 201
    reg_link = resp.json()["registrierungslink"]
    assert reg_link

    reg_token = await _extrahiere_token(reg_link)
    reg_resp = await client.post(
        "/api/partnerportal/auth/registrieren",
        json={"token": reg_token, "name": "Erika Muster", "password": "sicheres-passwort-123"},
    )
    assert reg_resp.status_code == 201
    me = await client.get(
        "/api/partnerportal/auth/me", headers=auth_headers(reg_resp.json()["access_token"])
    )
    assert me.status_code == 200
    assert me.json()["partner_name"] == "Elektro Subunternehmer KG"

    # Erneute Registrierung mit demselben Token ist nicht mehr moeglich.
    replay = await client.post(
        "/api/partnerportal/auth/registrieren",
        json={"token": reg_token, "name": "X", "password": "sicheres-passwort-123"},
    )
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_partner_einladung_widerrufen_sperrt_registrierung(
    client, make_mandant, make_user, make_partner
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    partner = await make_partner(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/partner/{partner.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "widerruf@partner.example.de"},
    )
    einladung_id = resp.json()["id"]
    reg_token = await _extrahiere_token(resp.json()["registrierungslink"])

    revoke = await client.delete(
        f"/api/partner/{partner.id}/einladungen/{einladung_id}", headers=auth_headers(token)
    )
    assert revoke.status_code == 204

    reg = await client.post(
        "/api/partnerportal/auth/registrieren",
        json={"token": reg_token, "name": "X", "password": "sicheres-passwort-123"},
    )
    assert reg.status_code == 400


@pytest.mark.asyncio
async def test_techniker_darf_partner_nicht_einladen(client, make_mandant, make_user, make_partner):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    partner = await make_partner(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/partner/{partner.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "verboten@partner.example.de"},
    )
    assert resp.status_code == 403


# --- Partnerportal: Auth ------------------------------------------------------


@pytest.mark.asyncio
async def test_partner_login_and_me(client, make_mandant, make_partner):
    mandant = await make_mandant()
    partner = await make_partner(mandant=mandant, name="Blitzschnell Elektro")
    zugang = await _make_zugang(mandant, partner, email="login@partner.example.de")

    tokens = await _partner_login(client, "login@partner.example.de", "partner-pw-123")
    assert tokens["access_token"]

    me = await client.get("/api/partnerportal/auth/me", headers=auth_headers(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["partner_name"] == "Blitzschnell Elektro"
    assert me.json()["zugang_id"] == str(zugang.id)


@pytest.mark.asyncio
async def test_partner_token_kann_nicht_gegen_interne_api_verwendet_werden(
    client, make_mandant, make_partner
):
    mandant = await make_mandant()
    partner = await make_partner(mandant=mandant)
    await _make_zugang(mandant, partner, email="x@partner.example.de")
    tokens = await _partner_login(client, "x@partner.example.de", "partner-pw-123")

    resp = await client.get("/api/kunden", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 401

    resp2 = await client.get("/api/partner", headers=auth_headers(tokens["access_token"]))
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_interner_token_kann_nicht_gegen_partnerportal_verwendet_werden(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/partnerportal/auftraege", headers=auth_headers(token))
    assert resp.status_code == 401


# --- Partnerportal: Sicht auf eigene Auftraege --------------------------------


@pytest.mark.asyncio
async def test_partner_sieht_nur_eigene_auftraege(
    client, make_mandant, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner_a = await make_partner(mandant=mandant, name="Partner A")
    partner_b = await make_partner(mandant=mandant, name="Partner B")
    vorgang_a = await make_vorgang(
        mandant=mandant, kunde=kunde, titel="Fuer Partner A",
        partner_id=partner_a.id, partner_freigabe_status="vorgeschlagen",
    )
    await make_vorgang(
        mandant=mandant, kunde=kunde, titel="Fuer Partner B",
        partner_id=partner_b.id, partner_freigabe_status="vorgeschlagen",
    )
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Nicht delegiert")

    await _make_zugang(mandant, partner_a, email="a@partner.example.de")
    tokens = await _partner_login(client, "a@partner.example.de", "partner-pw-123")

    resp = await client.get("/api/partnerportal/auftraege", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 200
    titel = [v["titel"] for v in resp.json()]
    assert titel == ["Fuer Partner A"]

    direct = await client.get(
        f"/api/partnerportal/auftraege/{vorgang_a.id}", headers=auth_headers(tokens["access_token"])
    )
    assert direct.status_code == 200
    assert "kundennummer" not in direct.json()
    assert "partner_honorar_netto" in direct.json()


@pytest.mark.asyncio
async def test_partner_kann_fremden_auftrag_nicht_per_id_abrufen(
    client, make_mandant, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner_a = await make_partner(mandant=mandant, name="Partner A")
    partner_b = await make_partner(mandant=mandant, name="Partner B")
    vorgang_b = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner_b.id, partner_freigabe_status="vorgeschlagen"
    )
    await _make_zugang(mandant, partner_a, email="a2@partner.example.de")
    tokens = await _partner_login(client, "a2@partner.example.de", "partner-pw-123")

    resp = await client.get(
        f"/api/partnerportal/auftraege/{vorgang_b.id}", headers=auth_headers(tokens["access_token"])
    )
    assert resp.status_code == 404


# --- Partnerportal: Annahme/Ablehnung -----------------------------------------


@pytest.mark.asyncio
async def test_partner_nimmt_auftrag_an(client, make_mandant, make_kunde, make_vorgang, make_partner):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen"
    )
    await _make_zugang(mandant, partner, email="annahme@partner.example.de")
    tokens = await _partner_login(client, "annahme@partner.example.de", "partner-pw-123")

    resp = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "angenommen"},
    )
    assert resp.status_code == 200
    assert resp.json()["partner_freigabe_status"] == "angenommen"

    # Doppelte Annahme ist kein gueltiger Uebergang mehr.
    resp2 = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "angenommen"},
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_partner_lehnt_auftrag_mit_grund_ab(client, make_mandant, make_kunde, make_vorgang, make_partner):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen"
    )
    await _make_zugang(mandant, partner, email="ablehnung@partner.example.de")
    tokens = await _partner_login(client, "ablehnung@partner.example.de", "partner-pw-123")

    resp = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "abgelehnt", "ablehnung_grund": "Kapazitaet fehlt diese Woche"},
    )
    assert resp.status_code == 200
    assert resp.json()["partner_freigabe_status"] == "abgelehnt"
    assert resp.json()["partner_ablehnung_grund"] == "Kapazitaet fehlt diese Woche"


@pytest.mark.asyncio
async def test_partner_kann_status_erst_nach_annahme_aendern(
    client, make_mandant, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen"
    )
    await _make_zugang(mandant, partner, email="status@partner.example.de")
    tokens = await _partner_login(client, "status@partner.example.de", "partner-pw-123")

    resp = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/status",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "in_arbeit"},
    )
    assert resp.status_code == 409

    await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "angenommen"},
    )
    resp2 = await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/status",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "in_arbeit"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "in_arbeit"


@pytest.mark.asyncio
async def test_partner_status_erlaubt_kein_abrechnet_oder_storniert(
    client, make_mandant, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="angenommen"
    )
    await _make_zugang(mandant, partner, email="illegal@partner.example.de")
    tokens = await _partner_login(client, "illegal@partner.example.de", "partner-pw-123")

    for verbotener_status in ("abgerechnet", "storniert"):
        resp = await client.patch(
            f"/api/partnerportal/auftraege/{vorgang.id}/status",
            headers=auth_headers(tokens["access_token"]),
            json={"status": verbotener_status},
        )
        assert resp.status_code == 422  # nicht Teil des erlaubten Literal-Sets


@pytest.mark.asyncio
async def test_partner_kann_kommentar_erst_nach_annahme_schreiben(
    client, make_mandant, make_kunde, make_vorgang, make_partner
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    partner = await make_partner(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, partner_id=partner.id, partner_freigabe_status="vorgeschlagen"
    )
    await _make_zugang(mandant, partner, email="kommentar@partner.example.de")
    tokens = await _partner_login(client, "kommentar@partner.example.de", "partner-pw-123")

    vorher = await client.post(
        f"/api/partnerportal/auftraege/{vorgang.id}/kommentare",
        headers=auth_headers(tokens["access_token"]),
        json={"body": "Sollte noch nicht gehen"},
    )
    assert vorher.status_code == 409

    await client.patch(
        f"/api/partnerportal/auftraege/{vorgang.id}/antwort",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "angenommen"},
    )
    nachher = await client.post(
        f"/api/partnerportal/auftraege/{vorgang.id}/kommentare",
        headers=auth_headers(tokens["access_token"]),
        json={"body": "Bin morgen vor Ort"},
    )
    assert nachher.status_code == 201
    assert nachher.json()["body"] == "Bin morgen vor Ort"
