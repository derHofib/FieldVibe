import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.services.pdf_service import generate_formular_pdf
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
async def test_felder_werden_beim_anlegen_automatisch_gestapelt(client, make_mandant, make_user):
    """Ohne explizites y_mm haengt create_formularfeld ein neues Feld
    unterhalb aller bestehenden Felder DERSELBEN Seite an -- Absicherung
    gegen versehentliche Ueberlappung bei der Standard-"Feld hinzufügen"-
    Bedienung."""
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
            json={"feld_typ": "text", "label": "A"},
        )
    ).json()
    feld_b = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "B"},
        )
    ).json()
    assert feld_a["y_mm"] == 0
    assert feld_b["y_mm"] == feld_a["hoehe_mm"]
    assert feld_a["reihenfolge"] == 0
    assert feld_b["reihenfolge"] == 1


@pytest.mark.asyncio
async def test_felder_positionen_bulk_update(client, make_mandant, make_user):
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
            json={"feld_typ": "text", "label": "A"},
        )
    ).json()
    feld_b = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "B"},
        )
    ).json()

    # Nebeneinander statt gestapelt anordnen.
    resp = await client.put(
        f"/api/formulare/{formular['id']}/felder/positionen",
        headers=auth_headers(token),
        json=[
            {"id": feld_a["id"], "seite": 0, "x_mm": 0, "y_mm": 0, "breite_mm": 90, "hoehe_mm": 8},
            {"id": feld_b["id"], "seite": 0, "x_mm": 90, "y_mm": 0, "breite_mm": 90, "hoehe_mm": 8},
        ],
    )
    assert resp.status_code == 200
    body = {f["id"]: f for f in resp.json()}
    assert body[feld_a["id"]]["x_mm"] == 0
    assert body[feld_b["id"]]["x_mm"] == 90
    assert body[feld_a["id"]]["reihenfolge"] == 0
    assert body[feld_b["id"]]["reihenfolge"] == 1


@pytest.mark.asyncio
async def test_ueberlappende_positionen_werden_akzeptiert(client, make_mandant, make_user):
    """Anders als beim frueheren 12-Spalten-Raster ist Ueberlappung bei der
    freien Positionierung erlaubt (wie im MS-Access-Formular-Designer) --
    das Backend blockt nicht mehr, der Editor markiert das nur optisch."""
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
            json={"feld_typ": "text", "label": "A"},
        )
    ).json()
    feld_b = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "B"},
        )
    ).json()

    resp = await client.put(
        f"/api/formulare/{formular['id']}/felder/positionen",
        headers=auth_headers(token),
        json=[
            {"id": feld_a["id"], "seite": 0, "x_mm": 0, "y_mm": 0, "breite_mm": 100, "hoehe_mm": 8},
            {"id": feld_b["id"], "seite": 0, "x_mm": 50, "y_mm": 0, "breite_mm": 100, "hoehe_mm": 8},
        ],
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_position_bounds_werden_validiert(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "F"})
    ).json()
    resp = await client.post(
        f"/api/formulare/{formular['id']}/felder",
        headers=auth_headers(token),
        json={"feld_typ": "text", "label": "Zu breit", "x_mm": 100, "breite_mm": 100},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_seite_ausserhalb_anzahl_seiten_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "F"})
    ).json()
    assert formular["anzahl_seiten"] == 1

    resp = await client.post(
        f"/api/formulare/{formular['id']}/felder",
        headers=auth_headers(token),
        json={"feld_typ": "text", "label": "X", "seite": 1},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_anzahl_seiten_erhoehen_und_verringern(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "F"})
    ).json()

    erhoeht = await client.patch(
        f"/api/formulare/{formular['id']}", headers=auth_headers(token), json={"anzahl_seiten": 2}
    )
    assert erhoeht.status_code == 200
    assert erhoeht.json()["anzahl_seiten"] == 2

    feld_auf_seite_2 = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "X", "seite": 1},
        )
    ).json()
    assert feld_auf_seite_2["seite"] == 1

    blockiert = await client.patch(
        f"/api/formulare/{formular['id']}", headers=auth_headers(token), json={"anzahl_seiten": 1}
    )
    assert blockiert.status_code == 409

    await client.delete(
        f"/api/formulare/{formular['id']}/felder/{feld_auf_seite_2['id']}", headers=auth_headers(token)
    )
    verringert = await client.patch(
        f"/api/formulare/{formular['id']}", headers=auth_headers(token), json={"anzahl_seiten": 1}
    )
    assert verringert.status_code == 200


@pytest.mark.asyncio
async def test_datenquelle_nur_fuer_passende_feldtypen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "F"})
    ).json()

    abgelehnt = await client.post(
        f"/api/formulare/{formular['id']}/felder",
        headers=auth_headers(token),
        json={"feld_typ": "dropdown", "label": "X", "datenquelle": "kunde.name"},
    )
    assert abgelehnt.status_code == 422

    erlaubt = await client.post(
        f"/api/formulare/{formular['id']}/felder",
        headers=auth_headers(token),
        json={"feld_typ": "text", "label": "Kunde", "datenquelle": "kunde.name"},
    )
    assert erlaubt.status_code == 201
    assert erlaubt.json()["datenquelle"] == "kunde.name"


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


@pytest.mark.asyncio
async def test_auto_fill_beim_start_vorbelegt_und_ueberschreibbar(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Café Sonnenschein")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    formular = (
        await client.post("/api/formulare", headers=auth_headers(token), json={"name": "Auto-Fill-Test"})
    ).json()
    feld = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "Kundenname", "datenquelle": "kunde.name"},
        )
    ).json()
    feld_ohne_quelle = (
        await client.post(
            f"/api/formulare/{formular['id']}/felder",
            headers=auth_headers(token),
            json={"feld_typ": "text", "label": "Notiz"},
        )
    ).json()

    start = (
        await client.post(
            f"/api/vorgang-formulare?vorgang_id={vorgang.id}",
            headers=auth_headers(token),
            json={"formular_id": formular["id"]},
        )
    ).json()
    assert start["antworten"][feld["id"]] == "Café Sonnenschein"
    assert feld_ohne_quelle["id"] not in start["antworten"]

    # Bleibt trotz Vorbelegung durch den Techniker ueberschreibbar.
    ueberschrieben = await client.patch(
        f"/api/vorgang-formulare/{start['id']}",
        headers=auth_headers(token),
        json={"antworten": {**start["antworten"], feld["id"]: "Anderer Name"}},
    )
    assert ueberschrieben.status_code == 200
    assert ueberschrieben.json()["antworten"][feld["id"]] == "Anderer Name"


def _fake_mandant(name: str = "Test GmbH") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _fake_vorgang(vorgangsnummer: str = "V-00001", titel: str = "Testvorgang") -> SimpleNamespace:
    return SimpleNamespace(vorgangsnummer=vorgangsnummer, titel=titel)


def test_pdf_export_legacy_snapshot_ohne_version_faellt_auf_flow_renderer_zurueck():
    """Ein VorgangFormular-Snapshot ohne snapshot_version stammt aus einer
    Ausfuellung von vor der Raster-Umstellung -- generate_formular_pdf muss
    dafuer weiterhin den urspruenglichen, rein sequenziellen Renderer
    verwenden, damit bereits ausgestellte PDFs bit-identisch bleiben."""
    vorgang_formular = SimpleNamespace(
        formular_snapshot={
            "name": "Altes Formular",
            "felder": [
                {"id": "f1", "feld_typ": "text", "label": "Notiz", "reihenfolge": 0, "pflichtfeld": False},
            ],
        },
        antworten={"f1": "Alles ok"},
        abgeschlossen_am=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    pdf_bytes = generate_formular_pdf(_fake_mandant(), _fake_vorgang(), vorgang_formular, bilder={})
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_export_raster_snapshot_mit_seitenumbruch():
    """40 volle Zeilen a 8mm sprengen definitiv eine A4-Seite -- erzwingt den
    Seitenumbruch-Zweig im Raster-Renderer (Feld wird komplett auf die
    naechste Seite verschoben statt angeschnitten)."""
    felder = [
        {
            "id": f"f{i}",
            "feld_typ": "text",
            "label": f"Feld {i}",
            "reihenfolge": i,
            "pflichtfeld": False,
            "raster_zeile": i,
            "raster_spalte": 0,
            "raster_breite": 12,
            "raster_hoehe": 1,
            "datenquelle": None,
        }
        for i in range(40)
    ]
    vorgang_formular = SimpleNamespace(
        formular_snapshot={
            "snapshot_version": 2,
            "name": "Grosses Formular",
            "zeilenhoehe_mm": 8,
            "felder": felder,
        },
        antworten={f["id"]: f"Wert {f['id']}" for f in felder},
        abgeschlossen_am=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    pdf_bytes = generate_formular_pdf(_fake_mandant(), _fake_vorgang(), vorgang_formular, bilder={})
    assert pdf_bytes.startswith(b"%PDF")
    seiten = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(seiten) >= 2


def test_pdf_export_freeform_snapshot_mit_mehreren_seiten():
    """snapshot_version 3 -- Seitenaufteilung ist explizit im Snapshot
    festgelegt (anzahl_seiten + Formularfeld.seite), kein automatischer
    Umbruch mehr. Zwei Felder auf Seite 0, eines auf Seite 1 muessen als
    genau zwei PDF-Seiten herauskommen."""
    felder = [
        {
            "id": "f0",
            "feld_typ": "text",
            "label": "Feld auf Seite 1",
            "reihenfolge": 0,
            "pflichtfeld": False,
            "seite": 0,
            "x_mm": 0,
            "y_mm": 0,
            "breite_mm": 90,
            "hoehe_mm": 8,
            "datenquelle": None,
        },
        {
            "id": "f1",
            "feld_typ": "text",
            "label": "Feld auf Seite 2",
            "reihenfolge": 1,
            "pflichtfeld": False,
            "seite": 1,
            "x_mm": 0,
            "y_mm": 0,
            "breite_mm": 90,
            "hoehe_mm": 8,
            "datenquelle": None,
        },
    ]
    vorgang_formular = SimpleNamespace(
        formular_snapshot={
            "snapshot_version": 3,
            "name": "Freiform-Formular",
            "anzahl_seiten": 2,
            "felder": felder,
        },
        antworten={f["id"]: f"Wert {f['id']}" for f in felder},
        abgeschlossen_am=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    pdf_bytes = generate_formular_pdf(_fake_mandant(), _fake_vorgang(), vorgang_formular, bilder={})
    assert pdf_bytes.startswith(b"%PDF")
    seiten = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(seiten) == 2
