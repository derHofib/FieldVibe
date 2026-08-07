import uuid

import pytest

from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from tests.conftest import auth_headers, login


async def _make_custom_mit_formulare_recht(mandant, *, aktionen: set[str]) -> AccountTyp:
    """Legt einen Account-Typ mit expliziten "formulare"-Rechten an -- die
    bestehenden Legacy-Rollen-Fixtures (siehe conftest._LEGACY_RECHTE)
    kennen den neuen Bereich "formulare" nicht, daher hier direkt."""
    async with system_session() as session:
        account_typ = AccountTyp(mandant_id=mandant.id, name=f"Formular-Rolle-{uuid.uuid4().hex[:6]}")
        session.add(account_typ)
        await session.flush()
        for aktion in aktionen:
            session.add(
                AccountTypRecht(
                    account_typ_id=account_typ.id, bereich="formulare", aktion=aktion, erlaubt=True
                )
            )
        # "vorgaenge:sehen" braucht jede Rolle, die vorgang-formulare
        # ansprechen soll (siehe require_recht("vorgaenge", "sehen") auf
        # app/api/routes/vorgang_formulare.py).
        session.add(
            AccountTypRecht(account_typ_id=account_typ.id, bereich="vorgaenge", aktion="sehen", erlaubt=True)
        )
        await session.flush()
        await session.refresh(account_typ)
        return account_typ


async def _make_custom_user(mandant, account_typ):
    from app.core.security import hash_password
    from app.models.user import User

    password = "hunter2!!"
    async with system_session() as session:
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password(password),
            role="custom",
            account_typ_id=account_typ.id,
            name="Formular-Tester",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_mandant_admin_kann_formular_mit_feldern_und_zuordnung_anlegen(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/formulare",
        headers=auth_headers(token),
        json={"name": "Wartungsprotokoll", "beschreibung": "Standard"},
    )
    assert resp.status_code == 201
    formular = resp.json()
    assert formular["felder"] == []
    assert formular["zuordnungen"] == []
    formular_id = formular["id"]

    feld_resp = await client.post(
        f"/api/formulare/{formular_id}/felder",
        headers=auth_headers(token),
        json={"feld_typ": "text", "label": "Anlage", "pflichtfeld": True, "reihenfolge": 0},
    )
    assert feld_resp.status_code == 201
    feld_id = feld_resp.json()["id"]

    zuordnung_resp = await client.post(
        f"/api/formulare/{formular_id}/zuordnungen",
        headers=auth_headers(token),
        json={"leistungstyp": "wartung", "pflicht_vor_abschluss": True},
    )
    assert zuordnung_resp.status_code == 201

    get_resp = await client.get(f"/api/formulare/{formular_id}", headers=auth_headers(token))
    body = get_resp.json()
    assert len(body["felder"]) == 1
    assert body["felder"][0]["id"] == feld_id
    assert len(body["zuordnungen"]) == 1
    assert body["zuordnungen"][0]["leistungstyp"] == "wartung"


@pytest.mark.asyncio
async def test_doppelte_zuordnung_gleicher_leistungstyp_wird_abgelehnt(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post(
            "/api/formulare", headers=auth_headers(token), json={"name": "Checkliste"}
        )
    ).json()
    await client.post(
        f"/api/formulare/{formular['id']}/zuordnungen",
        headers=auth_headers(token),
        json={"leistungstyp": "wartung"},
    )
    resp = await client.post(
        f"/api/formulare/{formular['id']}/zuordnungen",
        headers=auth_headers(token),
        json={"leistungstyp": "wartung"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_felder_umsortieren(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "F"})
    ).json()
    feld_a = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "A", "reihenfolge": 0},
        )
    ).json()
    feld_b = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "B", "reihenfolge": 1},
        )
    ).json()

    resp = await client.post(
        f"/api/formulare/{formular['id']}/felder/reihenfolge",
        headers=auth_headers(token),
        json=[feld_b["id"], feld_a["id"]],
    )
    assert resp.status_code == 200
    reihenfolgen = {f["id"]: f["reihenfolge"] for f in resp.json()}
    assert reihenfolgen[feld_b["id"]] == 0
    assert reihenfolgen[feld_a["id"]] == 1


@pytest.mark.asyncio
async def test_techniker_ohne_formulare_recht_bekommt_403(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/formulare", headers=auth_headers(token))
    assert resp.status_code == 403

    resp2 = await client.post(
        "/api/formulare", headers=auth_headers(token), json={"name": "x"}
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_custom_rolle_mit_formulare_recht_darf_anlegen(client, make_mandant):
    mandant = await make_mandant()
    account_typ = await _make_custom_mit_formulare_recht(mandant, aktionen={"sehen", "erstellen"})
    user = await _make_custom_user(mandant, account_typ)
    token = await login(client, user.email, "hunter2!!")

    resp = await client.post(
        "/api/formulare", headers=auth_headers(token), json={"name": "Erlaubt"}
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_rls_isolation_zwischen_mandanten(client, make_mandant, make_user):
    mandant_a = await make_mandant(name="A")
    mandant_b = await make_mandant(name="B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    formular = (
        await client.post(
            "/api/formulare", headers=auth_headers(token_a), json={"name": "Nur A"}
        )
    ).json()

    resp = await client.get(f"/api/formulare/{formular['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    list_resp = await client.get("/api/formulare", headers=auth_headers(token_b))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_ausfuellen_workflow_pflichtfeld_und_abschliessen(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="wartung")
    techniker_token = await login(client, techniker.email, "pw-123456")

    formular = (
        await client.post(
            "/api/formulare", headers=auth_headers(admin_token), json={"name": "Protokoll"}
        )
    ).json()
    feld = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(admin_token),
            json={"feld_typ": "text", "label": "Notiz", "pflichtfeld": True},
        )
    ).json()

    verfuegbar = await client.get(
        f"/api/vorgang-formulare/verfuegbar?vorgang_id={vorgang.id}",
        headers=auth_headers(techniker_token),
    )
    assert verfuegbar.status_code == 200
    assert verfuegbar.json() == []  # noch keine Zuordnung fuer "wartung"

    await client.post(
        f"/api/formulare/{formular['id']}/zuordnungen",
        headers=auth_headers(admin_token),
        json={"leistungstyp": "wartung"},
    )
    verfuegbar2 = await client.get(
        f"/api/vorgang-formulare/verfuegbar?vorgang_id={vorgang.id}",
        headers=auth_headers(techniker_token),
    )
    assert len(verfuegbar2.json()) == 1

    start = await client.post(
        f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
        headers=auth_headers(techniker_token),
        json={"formular_id": formular["id"]},
    )
    assert start.status_code == 201
    vf = start.json()
    assert vf["status"] == "offen"

    abschluss_ohne_pflichtfeld = await client.post(
        f"/api/vorgang-formulare/{vf['id']}/abschliessen", headers=auth_headers(techniker_token)
    )
    assert abschluss_ohne_pflichtfeld.status_code == 400

    patch_resp = await client.patch(
        f"/api/vorgang-formulare/{vf['id']}",
        headers=auth_headers(techniker_token),
        json={"antworten": {feld["id"]: "Alles ok"}},
    )
    assert patch_resp.status_code == 200

    abschluss = await client.post(
        f"/api/vorgang-formulare/{vf['id']}/abschliessen", headers=auth_headers(techniker_token)
    )
    assert abschluss.status_code == 200
    assert abschluss.json()["status"] == "abgeschlossen"

    events = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(techniker_token)
    )
    assert "formular" in [e["event_type"] for e in events.json()]


@pytest.mark.asyncio
async def test_pflicht_vor_abschluss_blockiert_vorgang_abschluss(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="wartung")

    formular = (
        await client.post(
            "/api/formulare", headers=auth_headers(token), json={"name": "Pflichtformular"}
        )
    ).json()
    await client.post(
        f"/api/formulare/{formular['id']}/zuordnungen",
        headers=auth_headers(token),
        json={"leistungstyp": "wartung", "pflicht_vor_abschluss": True},
    )

    blocked = await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert blocked.status_code == 409
    assert "Pflichtformular" in blocked.json()["detail"]

    start = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()
    await client.post(f"/api/vorgang-formulare/{start['id']}/abschliessen", headers=auth_headers(token))

    ok = await client.patch(
        f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "abgeschlossen"


@pytest.mark.asyncio
async def test_pdf_export_nur_wenn_abgeschlossen(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "PDF-Test"})
    ).json()
    start = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()

    noch_offen = await client.get(
        f"/api/vorgang-formulare/{start['id']}/pdf", headers=auth_headers(token)
    )
    assert noch_offen.status_code == 409

    await client.post(f"/api/vorgang-formulare/{start['id']}/abschliessen", headers=auth_headers(token))
    fertig = await client.get(f"/api/vorgang-formulare/{start['id']}/pdf", headers=auth_headers(token))
    assert fertig.status_code == 200
    assert fertig.headers["content-type"] == "application/pdf"
    assert fertig.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_snapshot_bleibt_stabil_nach_aenderung_der_vorlage(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "Original"})
    ).json()
    feld = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "Altes Label"},
        )
    ).json()

    start = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()
    assert start["formular_snapshot"]["felder"][0]["label"] == "Altes Label"

    await client.patch(
        f"/api/formulare/{formular['id']}/felder/{feld['id']}",
        headers=auth_headers(token),
        json={"label": "Neues Label"},
    )

    reread = await client.get(
        f"/api/vorgang-formulare/{start['id']}", headers=auth_headers(token)
    )
    assert reread.json()["formular_snapshot"]["felder"][0]["label"] == "Altes Label"


@pytest.mark.asyncio
async def test_kunde_beschraenkter_techniker_ohne_zuweisung_bekommt_404(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)  # keine Zuweisung an techniker
    techniker_token = await login(client, techniker.email, "pw-123456")

    resp = await client.get(
        f"/api/vorgang-formulare/verfuegbar?vorgang_id={vorgang.id}",
        headers=auth_headers(techniker_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_offenen_entwurf_verwerfen_aber_abgeschlossenen_nicht(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "Entwurf-Test"})
    ).json()
    start = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()

    delete_resp = await client.delete(
        f"/api/vorgang-formulare/{start['id']}", headers=auth_headers(token)
    )
    assert delete_resp.status_code == 204

    start2 = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()
    await client.post(f"/api/vorgang-formulare/{start2['id']}/abschliessen", headers=auth_headers(token))

    delete_abgeschlossen = await client.delete(
        f"/api/vorgang-formulare/{start2['id']}", headers=auth_headers(token)
    )
    assert delete_abgeschlossen.status_code == 409
