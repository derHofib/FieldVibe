"""Synchronisierung Altpfad (role/account_typ_id) -> Besetzungen (organigramm_sync_service)."""
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from app.services.user_anonymisierung_service import anonymisiere_user
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _aktive_positionen(user_id) -> dict[str, str]:
    """titel -> art der aktiven Besetzungen."""
    async with system_session() as session:
        zeilen = await session.execute(
            select(Position.titel, PositionBesetzung.art)
            .join(PositionBesetzung, PositionBesetzung.position_id == Position.id)
            .where(PositionBesetzung.user_id == UUID(str(user_id)), PositionBesetzung.gueltig_bis.is_(None))
        )
        return {t: a for t, a in zeilen}


async def _alle_besetzungen(user_id) -> list[PositionBesetzung]:
    async with system_session() as session:
        return list(
            (await session.execute(select(PositionBesetzung).where(PositionBesetzung.user_id == UUID(str(user_id)))))
            .scalars()
            .all()
        )


async def _typ(client, kopf, name, rechte=()):
    typ = (await client.post("/api/account-typen", headers=kopf, json={"name": name})).json()
    for bereich, aktion in rechte:
        await client.put(
            f"/api/account-typen/{typ['id']}/rechte", headers=kopf, json={"bereich": bereich, "aktion": aktion, "erlaubt": True}
        )
    return typ


async def _user_anlegen(client, kopf, mandant, email, typ_id):
    antwort = await client.post(
        "/api/users",
        headers=kopf,
        json={"mandant_id": str(mandant.id), "email": email, "password": "supersecret1", "role": "custom",
              "account_typ_id": typ_id, "name": email},
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


@pytest.mark.asyncio
async def test_account_typ_wechsel_verschiebt_besetzung_und_rechte(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = auth_headers(await login(client, admin.email, PW))
    dispo = await _typ(client, kopf, "Dispo", [("dispo", "sehen")])
    buchhaltung = await _typ(client, kopf, "Buchhaltung", [("abrechnung", "sehen")])
    user = await _user_anlegen(client, kopf, mandant, "wechsler@x.de", dispo["id"])
    assert await _aktive_positionen(user["id"]) == {"Dispo": "regulaer"}

    async def rechte():
        token = await login(client, "wechsler@x.de", "supersecret1")
        return (await client.get("/api/auth/me", headers=auth_headers(token))).json()["rechte"]

    assert (await rechte())["dispo"] == ["sehen"]

    r = await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"account_typ_id": buchhaltung["id"]})
    assert r.status_code == 200, r.text
    assert await _aktive_positionen(user["id"]) == {"Buchhaltung": "regulaer"}
    historie = await _alle_besetzungen(user["id"])
    assert len(historie) == 2 and sum(b.gueltig_bis is not None for b in historie) == 1
    meine = await rechte()
    assert meine["dispo"] == [] and meine["abrechnung"] == ["sehen"]

    # custom -> mandant_admin: Wurzelbesetzung, Typ-Position endet
    await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"role": "mandant_admin"})
    assert await _aktive_positionen(user["id"]) == {"Geschäftsführung": "regulaer"}
    # und zurueck
    await client.patch(
        f"/api/users/{user['id']}", headers=kopf, json={"role": "custom", "account_typ_id": dispo["id"]}
    )
    assert await _aktive_positionen(user["id"]) == {"Dispo": "regulaer"}

    # Deaktivieren beendet alle, Reaktivieren besetzt neu
    await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"aktiv": False})
    assert await _aktive_positionen(user["id"]) == {}
    await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"aktiv": True})
    assert await _aktive_positionen(user["id"]) == {"Dispo": "regulaer"}


@pytest.mark.asyncio
async def test_manuelle_besetzungen_bleiben_beim_sync_unberuehrt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = auth_headers(await login(client, admin.email, PW))
    dispo = await _typ(client, kopf, "Dispo")
    lager = await _typ(client, kopf, "Lager")
    user = await _user_anlegen(client, kopf, mandant, "manuell@x.de", dispo["id"])

    async with system_session() as session:
        manuell = Position(mandant_id=mandant.id, titel="Projektleitung Neubau")
        session.add(manuell)
        await session.flush()
        session.add(
            PositionBesetzung(mandant_id=mandant.id, position_id=manuell.id, user_id=UUID(user["id"]), art="vertretung")
        )

    await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"account_typ_id": lager["id"]})
    assert await _aktive_positionen(user["id"]) == {"Lager": "regulaer", "Projektleitung Neubau": "vertretung"}

    # Deaktivieren beendet dagegen alle Besetzungen
    await client.patch(f"/api/users/{user['id']}", headers=kopf, json={"aktiv": False})
    assert await _aktive_positionen(user["id"]) == {}


@pytest.mark.asyncio
async def test_anonymisieren_beendet_alle_besetzungen(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password=PW)
    assert await _aktive_positionen(user.id) == {"Techniker": "regulaer"}
    async with system_session() as session:
        await anonymisiere_user(session, await session.get(User, user.id))
    assert await _aktive_positionen(user.id) == {}


@pytest.mark.asyncio
async def test_neuer_account_typ_erzeugt_position_unter_wurzel_und_umbenennen_folgt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = auth_headers(await login(client, admin.email, PW))
    typ = await _typ(client, kopf, "Azubi")

    async def typ_positionen():
        async with system_session() as session:
            return list(
                (await session.execute(select(Position).where(Position.account_typ_id == UUID(typ["id"])))).scalars().all()
            )

    (position,) = await typ_positionen()
    async with system_session() as session:
        wurzel = (
            await session.execute(select(Position).where(Position.mandant_id == mandant.id, Position.parent_id.is_(None)))
        ).scalar_one()
    assert position.titel == "Azubi" and position.parent_id == wurzel.id and position.typ == "linie"

    await client.patch(f"/api/account-typen/{typ['id']}", headers=kopf, json={"name": "Auszubildende"})
    (position,) = await typ_positionen()
    assert position.titel == "Auszubildende"
    # Neuer Nutzer danach nutzt dieselbe Position (kein Duplikat)
    user = await _user_anlegen(client, kopf, mandant, "azubi@x.de", typ["id"])
    assert len(await typ_positionen()) == 1
    assert await _aktive_positionen(user["id"]) == {"Auszubildende": "regulaer"}


@pytest.mark.asyncio
async def test_neuer_mandant_erzeugt_wurzelposition(client, make_mandant, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password=PW)
    token = await login(client, super_admin.email, PW)
    r = await client.post(
        "/api/admin/mandanten", headers=auth_headers(token), json={"name": "Neu GmbH", "slug": "neu-gmbh"}
    )
    assert r.status_code == 201, r.text
    async with system_session() as session:
        positionen = (
            (await session.execute(select(Position).where(Position.mandant_id == UUID(r.json()["id"])))).scalars().all()
        )
    assert [(p.titel, p.parent_id) for p in positionen] == [("Geschäftsführung", None)]


@pytest.mark.asyncio
async def test_einladung_annehmen_besetzt_typ_position(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = auth_headers(await login(client, admin.email, PW))
    typ = await _typ(client, kopf, "Monteur", [("vorgaenge", "sehen")])
    einladung = await client.post(
        "/api/users/einladungen",
        headers=kopf,
        json={"email": "neu@example.de", "role": "custom", "account_typ_id": typ["id"]},
    )
    token = parse_qs(urlparse(einladung.json()["registrierungslink"]).query)["token"][0]
    reg = await client.post(
        "/api/auth/registrieren", json={"token": token, "name": "Neu", "password": "supersecret1"}
    )
    assert reg.status_code == 201
    me = (await client.get("/api/auth/me", headers=auth_headers(reg.json()["access_token"]))).json()
    assert me["rechte"]["vorgaenge"] == ["sehen"]
    assert await _aktive_positionen(me["id"]) == {"Monteur": "regulaer"}


@pytest.mark.asyncio
async def test_mandant_admin_hat_wurzelbesetzung_und_loesch_rollen_keine(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    ansicht = await make_user(mandant=mandant, role="loesch_ansicht", password=PW)
    assert await _aktive_positionen(admin.id) == {"Geschäftsführung": "regulaer"}
    assert await _aktive_positionen(ansicht.id) == {}
