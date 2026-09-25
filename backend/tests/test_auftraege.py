import uuid

import pytest

from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.auftrag import Auftrag
from app.core.security import hash_password
from app.models.user import User
from tests.conftest import auth_headers, login


async def _make_custom_mit_projekte_recht(mandant, *, aktionen: set[str]) -> AccountTyp:
    async with system_session() as session:
        account_typ = AccountTyp(mandant_id=mandant.id, name=f"Auftrag-Rolle-{uuid.uuid4().hex[:6]}")
        session.add(account_typ)
        await session.flush()
        for aktion in aktionen:
            session.add(
                AccountTypRecht(
                    account_typ_id=account_typ.id, bereich="projekte", aktion=aktion, erlaubt=True
                )
            )
        await session.flush()
        await session.refresh(account_typ)
        return account_typ


async def _make_custom_user(mandant, account_typ, *, password="hunter2!!"):
    async with system_session() as session:
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password(password),
            role="custom",
            account_typ_id=account_typ.id,
            name="Auftrag-Tester",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_auftrag_anlegen_ohne_projekt_und_kunde(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/auftraege", headers=auth_headers(token), json={"titel": "Wallbox-Serie Musterstraße"}
    )
    assert resp.status_code == 201
    auftrag = resp.json()
    assert auftrag["projekt_id"] is None
    assert auftrag["kunde_id"] is None
    assert auftrag["status"] == "offen"
    assert auftrag["vorgaenge_gesamt"] == 0


@pytest.mark.asyncio
async def test_auftrag_mit_projekt_und_kunde_anlegen_und_filtern(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Schreinerei Vogt")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Sanierung"})
    ).json()

    created = await client.post(
        "/api/auftraege",
        headers=auth_headers(token),
        json={"titel": "Elektro-Gewerk", "projekt_id": projekt["id"], "kunde_id": str(kunde.id)},
    )
    assert created.status_code == 201
    auftrag = created.json()
    assert auftrag["projekt_id"] == projekt["id"]
    assert auftrag["kunde_name"] == "Schreinerei Vogt"

    nach_projekt = await client.get(
        "/api/auftraege", headers=auth_headers(token), params={"projekt_id": projekt["id"]}
    )
    assert [a["id"] for a in nach_projekt.json()] == [auftrag["id"]]

    nach_kunde = await client.get(
        "/api/auftraege", headers=auth_headers(token), params={"kunde_id": str(kunde.id)}
    )
    assert [a["id"] for a in nach_kunde.json()] == [auftrag["id"]]


@pytest.mark.asyncio
async def test_auftrag_mit_unbekanntem_projekt_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/auftraege",
        headers=auth_headers(token),
        json={"titel": "X", "projekt_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_vorgang_mit_auftrag_verknuepfen_und_ueber_auftrag_id_filtern(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Elektro Nord")
    token = await login(client, admin.email, "pw-123456")

    auftrag = (
        await client.post("/api/auftraege", headers=auth_headers(token), json={"titel": "Sammelauftrag"})
    ).json()

    vorgang_resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Teilleistung 1",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
            "auftrag_id": auftrag["id"],
        },
    )
    assert vorgang_resp.status_code == 201
    vorgang = vorgang_resp.json()
    assert vorgang["auftrag_id"] == auftrag["id"]

    gefiltert = await client.get(
        "/api/vorgaenge", headers=auth_headers(token), params={"auftrag_id": auftrag["id"]}
    )
    assert [v["id"] for v in gefiltert.json()] == [vorgang["id"]]

    auftrag_gelesen = await client.get(f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token))
    assert auftrag_gelesen.json()["vorgaenge_gesamt"] == 1


@pytest.mark.asyncio
async def test_vorgang_mit_unbekanntem_auftrag_wird_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "X",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
            "auftrag_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auftrag_status_patch(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    auftrag = (
        await client.post("/api/auftraege", headers=auth_headers(token), json={"titel": "Status-Test"})
    ).json()

    resp = await client.patch(
        f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abgeschlossen"

    invalid = await client.patch(
        f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token), json={"status": "erfunden"}
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_auftrag_loeschen_laesst_vorgang_unangetastet(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    auftrag = (
        await client.post("/api/auftraege", headers=auth_headers(token), json={"titel": "Wird geloescht"})
    ).json()
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=uuid.UUID(auftrag["id"]))

    delete_resp = await client.delete(f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token))
    assert delete_resp.status_code == 204
    assert (
        await client.get(f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token))
    ).status_code == 404

    # Referenziell -- der Vorgang selbst bleibt aktiv, nur die Referenz
    # zeigt jetzt auf einen geloeschten Auftrag (gleiches Prinzip wie bei
    # geloeschtem Projekt, siehe test_projekte.py).
    async with system_session() as session:
        db_auftrag = await session.get(Auftrag, uuid.UUID(auftrag["id"]))
        assert db_auftrag.geloescht_am is not None

    vorgang_resp = await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    assert vorgang_resp.status_code == 200
    assert vorgang_resp.json()["auftrag_id"] == auftrag["id"]


@pytest.mark.asyncio
async def test_kunde_loeschen_kaskadiert_auf_auftraege(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    auftrag = (
        await client.post(
            "/api/auftraege",
            headers=auth_headers(token),
            json={"titel": "Haengt am Kunden", "kunde_id": str(kunde.id)},
        )
    ).json()

    delete_resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert delete_resp.status_code == 204

    assert (
        await client.get(f"/api/auftraege/{auftrag['id']}", headers=auth_headers(token))
    ).status_code == 404


@pytest.mark.asyncio
async def test_mandant_isolation_fuer_auftraege(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.post("/api/auftraege", headers=auth_headers(token1), json={"titel": "Nur Betrieb1"})

    resp = await client.get("/api/auftraege", headers=auth_headers(token2))
    assert resp.json() == []


@pytest.mark.asyncio
async def test_custom_ohne_recht_bekommt_403(client, make_mandant):
    mandant = await make_mandant()
    account_typ = await _make_custom_mit_projekte_recht(mandant, aktionen=set())
    user = await _make_custom_user(mandant, account_typ)
    token = await login(client, user.email, "hunter2!!")

    resp = await client.get("/api/auftraege", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_custom_mit_sehen_recht_darf_listen_aber_nicht_anlegen(client, make_mandant):
    mandant = await make_mandant()
    account_typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"sehen"})
    user = await _make_custom_user(mandant, account_typ)
    token = await login(client, user.email, "hunter2!!")

    list_resp = await client.get("/api/auftraege", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/auftraege", headers=auth_headers(token), json={"titel": "Darf ich nicht"}
    )
    assert create_resp.status_code == 403
