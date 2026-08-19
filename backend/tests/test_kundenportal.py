from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.kundenportal import KundenportalZugang
from app.models.mangel import Mangel
from app.models.rechnung import Rechnung
from app.models.vorgang_event import VorgangEvent
from tests.conftest import auth_headers, login


async def _make_zugang(mandant, kunde, *, email=None, password="kunden-pw-123", aktiv=True, name="Kundenportal-Nutzer"):
    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email=email or f"portal-{kunde.id}@example.de",
            password_hash=hash_password(password),
            name=name,
            aktiv=aktiv,
        )
        session.add(zugang)
        await session.flush()
        await session.refresh(zugang)
        zugang._plaintext_password = password
        return zugang


async def _kunden_login(client, email, password):
    resp = await client.post("/api/kundenportal/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()


@pytest.mark.asyncio
async def test_kunde_login_and_me(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant, name="Café Sonnenschein")
    zugang = await _make_zugang(mandant, kunde, email="kunde1@example.de")

    tokens = await _kunden_login(client, "kunde1@example.de", "kunden-pw-123")
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_resp = await client.get(
        "/api/kundenportal/auth/me", headers=auth_headers(tokens["access_token"])
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["kunde_id"] == str(kunde.id)
    assert body["kunde_name"] == "Café Sonnenschein"
    assert body["zugang_id"] == str(zugang.id)


@pytest.mark.asyncio
async def test_kunde_login_ignores_email_case(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="Kunde.Portal@Beispiel.DE")

    resp = await client.post(
        "/api/kundenportal/auth/login",
        json={"email": "kunde.portal@beispiel.de", "password": "kunden-pw-123"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_kunde_login_wrong_password_rejected(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde2@example.de")

    resp = await client.post(
        "/api/kundenportal/auth/login", json={"email": "kunde2@example.de", "password": "falsch"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_inactive_zugang_cannot_login(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde3@example.de", aktiv=False)

    resp = await client.post(
        "/api/kundenportal/auth/login", json={"email": "kunde3@example.de", "password": "kunden-pw-123"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_kunde_token_cannot_access_staff_endpoints(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde4@example.de")
    tokens = await _kunden_login(client, "kunde4@example.de", "kunden-pw-123")

    resp = await client.get("/api/kunden", headers=auth_headers(tokens["access_token"]))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_staff_token_cannot_access_kundenportal_endpoints(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/kundenportal/vorgaenge", headers=auth_headers(token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_flow(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde5@example.de")
    tokens = await _kunden_login(client, "kunde5@example.de", "kunden-pw-123")

    refresh_resp = await client.post(
        "/api/kundenportal/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert new_tokens["access_token"]

    me_resp = await client.get(
        "/api/kundenportal/auth/me", headers=auth_headers(new_tokens["access_token"])
    )
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_staff_refresh_token_rejected_on_kundenportal_refresh(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    login_resp = await client.post(
        "/api/auth/login", json={"email": admin.email, "password": "pw-123456"}
    )
    staff_refresh = login_resp.json()["refresh_token"]

    resp = await client.post("/api/kundenportal/auth/refresh", json={"refresh_token": staff_refresh})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_kunde_sees_only_own_vorgaenge_und_kundensichtbare_events(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Eigener Kunde")
    kunde2 = await make_kunde(mandant=mandant, name="Fremder Kunde")
    eigener_vorgang = await make_vorgang(mandant=mandant, kunde=kunde1, titel="Mein Auftrag")
    fremder_vorgang = await make_vorgang(mandant=mandant, kunde=kunde2, titel="Fremder Auftrag")
    await _make_zugang(mandant, kunde1, email="kunde6@example.de")
    admin_token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        session.add(
            VorgangEvent(
                mandant_id=mandant.id,
                vorgang_id=eigener_vorgang.id,
                event_type="kommentar",
                body="Sichtbar für Kunde",
                kundensichtbar=True,
            )
        )
        session.add(
            VorgangEvent(
                mandant_id=mandant.id,
                vorgang_id=eigener_vorgang.id,
                event_type="kommentar",
                body="Interner Vermerk",
                kundensichtbar=False,
            )
        )
        await session.commit()

    tokens = await _kunden_login(client, "kunde6@example.de", "kunden-pw-123")
    headers = auth_headers(tokens["access_token"])

    list_resp = await client.get("/api/kundenportal/vorgaenge", headers=headers)
    assert list_resp.status_code == 200
    ids = [v["id"] for v in list_resp.json()]
    assert str(eigener_vorgang.id) in ids
    assert str(fremder_vorgang.id) not in ids

    # Fremden Vorgang direkt abrufen -> 404, nicht 403 (keine Existenz-Info leaken)
    foreign_resp = await client.get(f"/api/kundenportal/vorgaenge/{fremder_vorgang.id}", headers=headers)
    assert foreign_resp.status_code == 404

    events_resp = await client.get(
        f"/api/kundenportal/vorgaenge/{eigener_vorgang.id}/events", headers=headers
    )
    assert events_resp.status_code == 200
    bodies = [e["body"] for e in events_resp.json()]
    assert "Sichtbar für Kunde" in bodies
    assert "Interner Vermerk" not in bodies


@pytest.mark.asyncio
async def test_kunde_kann_angebot_annehmen_und_reparatur_vorgang_entsteht(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await _make_zugang(mandant, kunde, email="kunde7@example.de")
    admin_token = await login(client, admin.email, "pw-123456")

    async with system_session() as session:
        mangel = Mangel(
            mandant_id=mandant.id, vorgang_id=vorgang.id, beschreibung="Kabelbruch", gemeldet_von=admin.id
        )
        session.add(mangel)
        await session.flush()
        mangel_id = mangel.id
        await session.commit()

    created = await client.post(
        "/api/angebote/from-maengel",
        headers=auth_headers(admin_token),
        json={"mangel_ids": [str(mangel_id)]},
    )
    angebot_id = created.json()["id"]
    await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(admin_token), json={"status": "versendet"}
    )

    kunde_tokens = await _kunden_login(client, "kunde7@example.de", "kunden-pw-123")
    kunde_headers = auth_headers(kunde_tokens["access_token"])

    accept_resp = await client.patch(
        f"/api/kundenportal/angebote/{angebot_id}", headers=kunde_headers, json={"status": "angenommen"}
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["angenommen_am"] is not None

    async with system_session() as session:
        refreshed_mangel = await session.get(Mangel, mangel_id)
        assert refreshed_mangel.status == "in_bearbeitung"
        assert refreshed_mangel.reparatur_vorgang_id is not None

    # VorgangEvent des Angebots wurde ohne Author gepostet (Kunde hat keinen User-Account)
    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(admin_token)
    )
    angebot_events = [e for e in events_resp.json() if e["event_type"] == "angebot"]
    assert any(e["author_user_id"] is None for e in angebot_events)


@pytest.mark.asyncio
async def test_kunde_kann_angebot_ablehnen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde8@example.de")
    admin_token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/angebote",
        headers=auth_headers(admin_token),
        json={
            "kunde_id": str(kunde.id),
            "positionen": [{"beschreibung": "Test", "einzelpreis": "10.00"}],
        },
    )
    angebot_id = created.json()["id"]
    await client.patch(
        f"/api/angebote/{angebot_id}", headers=auth_headers(admin_token), json={"status": "versendet"}
    )

    kunde_tokens = await _kunden_login(client, "kunde8@example.de", "kunden-pw-123")
    reject_resp = await client.patch(
        f"/api/kundenportal/angebote/{angebot_id}",
        headers=auth_headers(kunde_tokens["access_token"]),
        json={"status": "abgelehnt"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["abgelehnt_am"] is not None


@pytest.mark.asyncio
async def test_kunde_darf_nicht_direkt_versenden(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde9@example.de")

    async with system_session() as session:
        angebot = Angebot(
            mandant_id=mandant.id, kunde_id=kunde.id, angebotsnummer="A-TEST-1", erstellt_von=admin.id
        )
        session.add(angebot)
        await session.flush()
        angebot_id = angebot.id
        await session.commit()

    tokens = await _kunden_login(client, "kunde9@example.de", "kunden-pw-123")
    resp = await client.patch(
        f"/api/kundenportal/angebote/{angebot_id}",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "versendet"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_kunde_sieht_nur_eigene_rechnungen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant)
    kunde2 = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde1, email="kunde10@example.de")

    async with system_session() as session:
        r1 = Rechnung(
            mandant_id=mandant.id,
            kunde_id=kunde1.id,
            rechnungsnummer="R-TEST-1",
            betrag_netto=Decimal("100"),
            erstellt_von=admin.id,
        )
        r2 = Rechnung(
            mandant_id=mandant.id,
            kunde_id=kunde2.id,
            rechnungsnummer="R-TEST-2",
            betrag_netto=Decimal("200"),
            erstellt_von=admin.id,
        )
        session.add_all([r1, r2])
        await session.flush()
        r1_id, r2_id = r1.id, r2.id
        await session.commit()

    tokens = await _kunden_login(client, "kunde10@example.de", "kunden-pw-123")
    headers = auth_headers(tokens["access_token"])

    list_resp = await client.get("/api/kundenportal/rechnungen", headers=headers)
    ids = [r["id"] for r in list_resp.json()]
    assert str(r1_id) in ids
    assert str(r2_id) not in ids

    foreign_resp = await client.get(f"/api/kundenportal/rechnungen/{r2_id}", headers=headers)
    assert foreign_resp.status_code == 404

    pdf_resp = await client.get(f"/api/kundenportal/rechnungen/{r1_id}/pdf", headers=headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"


async def _extrahiere_token(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.asyncio
async def test_staff_invites_and_kunde_registriert_sich(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    einladen_resp = await client.post(
        f"/api/kunden/{kunde.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "neuer-zugang@example.de"},
    )
    assert einladen_resp.status_code == 201
    reg_link = einladen_resp.json()["registrierungslink"]
    assert reg_link  # kein SMTP konfiguriert -> Link kommt direkt zurueck

    duplicate_resp = await client.post(
        f"/api/kunden/{kunde.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "neuer-zugang@example.de"},
    )
    assert duplicate_resp.status_code == 409  # bereits eine offene Einladung fuer diese E-Mail

    reg_token = await _extrahiere_token(reg_link)
    too_short_resp = await client.post(
        "/api/kundenportal/auth/registrieren",
        json={"token": reg_token, "name": "Max Mustermann", "password": "zu-kurz"},
    )
    assert too_short_resp.status_code == 400

    register_resp = await client.post(
        "/api/kundenportal/auth/registrieren",
        json={"token": reg_token, "name": "Max Mustermann", "password": "sicheres-passwort-123"},
    )
    assert register_resp.status_code == 201
    assert register_resp.json()["access_token"]

    list_resp = await client.get(f"/api/kunden/{kunde.id}/portal-zugaenge", headers=auth_headers(token))
    assert len(list_resp.json()) == 1

    deactivate_resp = await client.patch(
        f"/api/kunden/{kunde.id}/portal-zugaenge/{list_resp.json()[0]['id']}",
        headers=auth_headers(token),
        json={"aktiv": False},
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["aktiv"] is False


@pytest.mark.asyncio
async def test_techniker_cannot_invite_kunde(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/kunden/{kunde.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "x@example.de"},
    )
    assert resp.status_code == 403
