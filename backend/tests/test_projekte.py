import uuid

import pytest

from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.projekt import Projekt, ProjektAufgabe
from app.models.user import User
from app.core.security import hash_password
from tests.conftest import auth_headers, login


async def _make_custom_mit_projekte_recht(mandant, *, aktionen: set[str]) -> AccountTyp:
    """Analog zu test_partner.py:_make_custom_mit_partner_recht -- die
    Legacy-Rollen-Fixtures kennen den neuen Bereich "projekte" nicht."""
    async with system_session() as session:
        account_typ = AccountTyp(mandant_id=mandant.id, name=f"Projekt-Rolle-{uuid.uuid4().hex[:6]}")
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
            name="Projekt-Tester",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_projekt_anlegen_erzeugt_standardspalten(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/projekte", headers=auth_headers(token), json={"name": "Website-Relaunch"}
    )
    assert resp.status_code == 201
    projekt_id = resp.json()["id"]

    spalten_resp = await client.get(f"/api/projekte/{projekt_id}/spalten", headers=auth_headers(token))
    assert [s["name"] for s in spalten_resp.json()] == ["Offen", "In Arbeit", "Review", "Fertig"]
    assert [s["reihenfolge"] for s in spalten_resp.json()] == [0, 1, 2, 3]


@pytest.mark.asyncio
async def test_custom_ohne_recht_bekommt_403(client, make_mandant):
    mandant = await make_mandant()
    account_typ = await _make_custom_mit_projekte_recht(mandant, aktionen=set())
    user = await _make_custom_user(mandant, account_typ)
    token = await login(client, user.email, "hunter2!!")

    resp = await client.get("/api/projekte", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_custom_mit_sehen_recht_darf_listen_aber_nicht_anlegen(client, make_mandant):
    mandant = await make_mandant()
    account_typ = await _make_custom_mit_projekte_recht(mandant, aktionen={"sehen"})
    user = await _make_custom_user(mandant, account_typ)
    token = await login(client, user.email, "hunter2!!")

    list_resp = await client.get("/api/projekte", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/projekte", headers=auth_headers(token), json={"name": "Darf ich nicht"}
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_aufgabe_anlegen_und_zwischen_spalten_verschieben(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Intern"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()
    offen_id = spalten[0]["id"]
    in_arbeit_id = spalten[1]["id"]

    created = await client.post(
        "/api/projekt-aufgaben",
        headers=auth_headers(token),
        json={
            "projekt_id": projekt["id"],
            "spalte_id": offen_id,
            "titel": "Angebote vergleichen",
            "prioritaet": "hoch",
            "checkliste": [{"text": "Anbieter A anfragen", "erledigt": False}],
        },
    )
    assert created.status_code == 201
    aufgabe = created.json()
    assert aufgabe["spalte_id"] == offen_id
    assert aufgabe["prioritaet"] == "hoch"
    assert aufgabe["checkliste"] == [{"text": "Anbieter A anfragen", "erledigt": False}]

    moved = await client.patch(
        f"/api/projekt-aufgaben/{aufgabe['id']}",
        headers=auth_headers(token),
        json={"spalte_id": in_arbeit_id},
    )
    assert moved.status_code == 200
    assert moved.json()["spalte_id"] == in_arbeit_id


@pytest.mark.asyncio
async def test_aufgabe_mit_fremder_spalte_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt_a = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "A"})
    ).json()
    projekt_b = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "B"})
    ).json()
    spalten_b = (
        await client.get(f"/api/projekte/{projekt_b['id']}/spalten", headers=auth_headers(token))
    ).json()

    resp = await client.post(
        "/api/projekt-aufgaben",
        headers=auth_headers(token),
        json={"projekt_id": projekt_a["id"], "spalte_id": spalten_b[0]["id"], "titel": "Fehlgriff"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_aufgabe_mit_vorgang_verknuepfen_und_ueber_vorgang_id_filtern(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Schreinerei Vogt")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Relaunch"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()

    await client.post(
        "/api/projekt-aufgaben",
        headers=auth_headers(token),
        json={
            "projekt_id": projekt["id"],
            "spalte_id": spalten[0]["id"],
            "titel": "Fotomaterial anfordern",
            "vorgang_id": str(vorgang.id),
        },
    )

    resp = await client.get(
        "/api/projekt-aufgaben", headers=auth_headers(token), params={"vorgang_id": str(vorgang.id)}
    )
    assert resp.status_code == 200
    [aufgabe] = resp.json()
    assert aufgabe["vorgang_id"] == str(vorgang.id)
    assert aufgabe["vorgang_vorgangsnummer"] == vorgang.vorgangsnummer
    assert aufgabe["vorgang_kunde_name"] == "Schreinerei Vogt"


@pytest.mark.asyncio
async def test_aufgabe_mit_unbekanntem_vorgang_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "X"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()

    resp = await client.post(
        "/api/projekt-aufgaben",
        headers=auth_headers(token),
        json={
            "projekt_id": projekt["id"],
            "spalte_id": spalten[0]["id"],
            "titel": "Y",
            "vorgang_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_spalte_loeschen_mit_offenen_aufgaben_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Y"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()
    offen_id = spalten[0]["id"]

    await client.post(
        "/api/projekt-aufgaben",
        headers=auth_headers(token),
        json={"projekt_id": projekt["id"], "spalte_id": offen_id, "titel": "Blockt Loeschung"},
    )

    resp = await client.delete(
        f"/api/projekte/{projekt['id']}/spalten/{offen_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 400

    leere_spalte_resp = await client.delete(
        f"/api/projekte/{projekt['id']}/spalten/{spalten[3]['id']}", headers=auth_headers(token)
    )
    assert leere_spalte_resp.status_code == 204


@pytest.mark.asyncio
async def test_projekt_loeschen_wandert_aufgaben_in_papierkorb(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Z"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()
    aufgabe = (
        await client.post(
            "/api/projekt-aufgaben",
            headers=auth_headers(token),
            json={"projekt_id": projekt["id"], "spalte_id": spalten[0]["id"], "titel": "Kind"},
        )
    ).json()

    delete_resp = await client.delete(f"/api/projekte/{projekt['id']}", headers=auth_headers(token))
    assert delete_resp.status_code == 204

    assert (await client.get(f"/api/projekte/{projekt['id']}", headers=auth_headers(token))).status_code == 404
    assert (
        await client.get(f"/api/projekt-aufgaben/{aufgabe['id']}", headers=auth_headers(token))
    ).status_code == 404

    # /api/papierkorb ist absichtlich nur loesch_ansicht/loesch_operativ
    # vorbehalten (nicht mandant_admin) -- die Kaskade selbst wird deshalb
    # direkt in der DB geprueft statt ueber diesen Endpoint.
    async with system_session() as session:
        db_projekt = await session.get(Projekt, projekt["id"])
        db_aufgabe = await session.get(ProjektAufgabe, aufgabe["id"])
        assert db_projekt.geloescht_am is not None
        assert db_aufgabe.geloescht_am is not None


@pytest.mark.asyncio
async def test_mandant_isolation_fuer_projekte(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.post("/api/projekte", headers=auth_headers(token1), json={"name": "Nur Betrieb1"})

    resp = await client.get("/api/projekte", headers=auth_headers(token2))
    assert resp.json() == []


@pytest.mark.asyncio
async def test_checkliste_wird_beim_patch_komplett_ersetzt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Check"})
    ).json()
    spalten = (
        await client.get(f"/api/projekte/{projekt['id']}/spalten", headers=auth_headers(token))
    ).json()
    aufgabe = (
        await client.post(
            "/api/projekt-aufgaben",
            headers=auth_headers(token),
            json={
                "projekt_id": projekt["id"],
                "spalte_id": spalten[0]["id"],
                "titel": "Checkliste",
                "checkliste": [{"text": "Eins", "erledigt": False}, {"text": "Zwei", "erledigt": False}],
            },
        )
    ).json()

    resp = await client.patch(
        f"/api/projekt-aufgaben/{aufgabe['id']}",
        headers=auth_headers(token),
        json={"checkliste": [{"text": "Eins", "erledigt": True}]},
    )
    assert resp.status_code == 200
    assert resp.json()["checkliste"] == [{"text": "Eins", "erledigt": True}]
