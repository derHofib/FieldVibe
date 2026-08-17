import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.account_typ import AccountTyp
from tests.conftest import auth_headers, login


async def _account_typ_darf_uebernehmen_setzen(mandant_id, *, erlaubt: bool) -> None:
    async with system_session() as session:
        result = await session.execute(
            select(AccountTyp).where(AccountTyp.mandant_id == mandant_id, AccountTyp.name == "Techniker")
        )
        account_typ = result.scalar_one()
        account_typ.darf_vorgaenge_selbst_uebernehmen = erlaubt
        await session.flush()


async def _neuer_vorgang(client, token, kunde_id: str) -> dict:
    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": kunde_id,
            "titel": "Sicherung ausgelöst",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_mandant_admin_darf_immer_uebernehmen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    vorgang = await _neuer_vorgang(client, token, str(kunde.id))
    assert vorgang["status"] == "neu"

    resp = await client.post(
        f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["zugewiesener_user_id"] == str(admin.id)
    assert body["zugewiesener_name"] == admin.name
    assert body["status"] == "in_arbeit"


@pytest.mark.asyncio
async def test_techniker_ohne_recht_darf_nicht_uebernehmen(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="admin-pw-1")
    admin_token = await login(client, admin.email, "admin-pw-1")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await _neuer_vorgang(client, admin_token, str(kunde.id))

    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    await _account_typ_darf_uebernehmen_setzen(mandant.id, erlaubt=False)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_mit_recht_darf_uebernehmen(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="admin-pw-2")
    admin_token = await login(client, admin.email, "admin-pw-2")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await _neuer_vorgang(client, admin_token, str(kunde.id))

    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    await _account_typ_darf_uebernehmen_setzen(mandant.id, erlaubt=True)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["zugewiesener_user_id"] == str(techniker.id)
    assert body["status"] == "in_arbeit"


@pytest.mark.asyncio
async def test_bereits_zugewiesenen_vorgang_darf_ein_anderer_uebernehmen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin_a = await make_user(mandant=mandant, role="mandant_admin", password="pw-a-123456")
    admin_b = await make_user(mandant=mandant, role="mandant_admin", password="pw-b-123456")
    kunde = await make_kunde(mandant=mandant)
    token_a = await login(client, admin_a.email, "pw-a-123456")
    token_b = await login(client, admin_b.email, "pw-b-123456")
    vorgang = await _neuer_vorgang(client, token_a, str(kunde.id))

    erst = await client.post(f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token_a))
    assert erst.json()["zugewiesener_user_id"] == str(admin_a.id)

    zweit = await client.post(f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token_b))
    assert zweit.status_code == 200
    assert zweit.json()["zugewiesener_user_id"] == str(admin_b.id)
    # Status bleibt "in_arbeit" -- nur der allererste Uebernehmen-Aufruf
    # transitioniert von "neu", ein Reassign aendert den Status nicht erneut.
    assert zweit.json()["status"] == "in_arbeit"


@pytest.mark.asyncio
async def test_geschlossenen_vorgang_darf_niemand_uebernehmen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    vorgang = await _neuer_vorgang(client, token, str(kunde.id))

    storno = await client.patch(
        f"/api/vorgaenge/{vorgang['id']}", headers=auth_headers(token), json={"status": "storniert"}
    )
    assert storno.status_code == 200

    resp = await client.post(f"/api/vorgaenge/{vorgang['id']}/uebernehmen", headers=auth_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_manuelle_zuweisung_per_patch(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="admin-pw-3")
    other = await make_user(mandant=mandant, role="mandant_admin", password="other-pw-3", name="Other Admin")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "admin-pw-3")
    vorgang = await _neuer_vorgang(client, token, str(kunde.id))

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang['id']}",
        headers=auth_headers(token),
        json={"zugewiesener_user_id": str(other.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["zugewiesener_user_id"] == str(other.id)
    assert body["zugewiesener_name"] == "Other Admin"
    # Manuelle Zuweisung aendert den Status nicht -- anders als beim
    # dedizierten Uebernehmen-Endpoint.
    assert body["status"] == "neu"

    aufheben = await client.patch(
        f"/api/vorgaenge/{vorgang['id']}",
        headers=auth_headers(token),
        json={"zugewiesener_user_id": None},
    )
    assert aufheben.status_code == 200
    assert aufheben.json()["zugewiesener_user_id"] is None


@pytest.mark.asyncio
async def test_me_spiegelt_darf_vorgaenge_selbst_uebernehmen(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="admin-pw-4")
    admin_token = await login(client, admin.email, "admin-pw-4")
    me_admin = await client.get("/api/auth/me", headers=auth_headers(admin_token))
    assert me_admin.json()["darf_vorgaenge_selbst_uebernehmen"] is True

    kunde = await make_kunde(mandant=mandant)
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    await _account_typ_darf_uebernehmen_setzen(mandant.id, erlaubt=False)
    token = await login(client, techniker.email, "pw-123456")
    me_ohne = await client.get("/api/auth/me", headers=auth_headers(token))
    assert me_ohne.json()["darf_vorgaenge_selbst_uebernehmen"] is False

    await _account_typ_darf_uebernehmen_setzen(mandant.id, erlaubt=True)
    token2 = await login(client, techniker.email, "pw-123456")
    me_mit = await client.get("/api/auth/me", headers=auth_headers(token2))
    assert me_mit.json()["darf_vorgaenge_selbst_uebernehmen"] is True
