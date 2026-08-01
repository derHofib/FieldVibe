import uuid

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.kundenportal import KundenportalZugang
from tests.conftest import auth_headers, login


async def _make_zugang(mandant, kunde, *, email=None, password="kunden-pw-123", name="Portal-Kontakt"):
    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email=email or f"portal-{kunde.id}@example.de",
            password_hash=hash_password(password),
            name=name,
            login_slug=uuid.uuid4().hex,
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


# --- Standorte ---------------------------------------------------------


@pytest.mark.asyncio
async def test_standort_crud_und_aktiv_filter(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Filiale Nord"},
    )
    assert create.status_code == 201
    standort_id = create.json()["id"]
    assert create.json()["aktiv"] is True

    # Standort inaktiv stellen
    patch = await client.patch(
        f"/api/standorte/{standort_id}", headers=auth_headers(token), json={"aktiv": False}
    )
    assert patch.status_code == 200
    assert patch.json()["aktiv"] is False

    listed = await client.get(
        f"/api/standorte?kunde_id={kunde.id}&aktiv=true", headers=auth_headers(token)
    )
    assert listed.json() == []


@pytest.mark.asyncio
async def test_inaktiver_standort_kann_nicht_fuer_neuen_vorgang_gewaehlt_werden(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    standort = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Filiale Süd"},
    )
    standort_id = standort.json()["id"]
    await client.patch(f"/api/standorte/{standort_id}", headers=auth_headers(token), json={"aktiv": False})

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "standort_id": standort_id,
            "titel": "Termin",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_inaktive_anlage_kann_nicht_fuer_neuen_vorgang_gewaehlt_werden(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.patch(f"/api/anlagen/{anlage.id}", headers=auth_headers(token), json={"aktiv": False})

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": str(anlage.id),
            "titel": "Termin",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 400


# --- Auftragsanfragen ----------------------------------------------------


@pytest.mark.asyncio
async def test_kunde_stellt_anfrage_und_disponent_nimmt_an(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde@example.de")

    kunden_tokens = await _kunden_login(client, "kunde@example.de", "kunden-pw-123")
    anfrage_resp = await client.post(
        "/api/kundenportal/anfragen",
        headers=auth_headers(kunden_tokens["access_token"]),
        json={"titel": "Steckdose defekt", "leistungstyp": "stoerung"},
    )
    assert anfrage_resp.status_code == 201
    anfrage = anfrage_resp.json()
    assert anfrage["status"] == "offen"

    staff_token = await login(client, disponent.email, "pw-123456")
    liste = await client.get("/api/vorgang-anfragen?status=offen", headers=auth_headers(staff_token))
    assert liste.status_code == 200
    assert len(liste.json()) == 1

    annehmen = await client.post(
        f"/api/vorgang-anfragen/{anfrage['id']}/annehmen",
        headers=auth_headers(staff_token),
        json={"abrechnungsart": "aufwand"},
    )
    assert annehmen.status_code == 200
    body = annehmen.json()
    assert body["status"] == "angenommen"
    assert body["vorgang_id"] is not None

    vorgang = await client.get(f"/api/vorgaenge/{body['vorgang_id']}", headers=auth_headers(staff_token))
    assert vorgang.status_code == 200
    assert vorgang.json()["titel"] == "Steckdose defekt"
    assert vorgang.json()["erstellt_von_kundenportal_zugang_id"] is not None

    # Kunde sieht seine eigene, nun angenommene Anfrage.
    eigene = await client.get(
        "/api/kundenportal/anfragen", headers=auth_headers(kunden_tokens["access_token"])
    )
    assert eigene.json()[0]["status"] == "angenommen"


@pytest.mark.asyncio
async def test_disponent_lehnt_anfrage_ab(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde2@example.de")

    kunden_tokens = await _kunden_login(client, "kunde2@example.de", "kunden-pw-123")
    anfrage_resp = await client.post(
        "/api/kundenportal/anfragen",
        headers=auth_headers(kunden_tokens["access_token"]),
        json={"titel": "Beratung PV-Anlage", "leistungstyp": "beratung"},
    )
    anfrage_id = anfrage_resp.json()["id"]

    staff_token = await login(client, disponent.email, "pw-123456")
    ablehnen = await client.post(
        f"/api/vorgang-anfragen/{anfrage_id}/ablehnen",
        headers=auth_headers(staff_token),
        json={"ablehnungsgrund": "Außerhalb unseres Einzugsgebiets"},
    )
    assert ablehnen.status_code == 200
    assert ablehnen.json()["status"] == "abgelehnt"

    # Ein zweites Mal bearbeiten ist nicht mehr moeglich.
    erneut = await client.post(
        f"/api/vorgang-anfragen/{anfrage_id}/annehmen",
        headers=auth_headers(staff_token),
        json={"abrechnungsart": "aufwand"},
    )
    assert erneut.status_code == 409


@pytest.mark.asyncio
async def test_kunde_kann_nicht_fremde_anfrage_annehmen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="kunde3@example.de")

    kunden_tokens = await _kunden_login(client, "kunde3@example.de", "kunden-pw-123")
    resp = await client.post(
        f"/api/vorgang-anfragen/{uuid.uuid4()}/annehmen",
        headers=auth_headers(kunden_tokens["access_token"]),
        json={"abrechnungsart": "aufwand"},
    )
    # Kundenportal-Token ist fuer Staff-Routen grundsaetzlich nicht gueltig.
    assert resp.status_code == 401


# --- Personalisierter Login-Link -----------------------------------------


@pytest.mark.asyncio
async def test_personalisierter_link_liefert_nur_anzeigedaten(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Bäckerei Krause")
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        f"/api/kunden/{kunde.id}/portal-zugaenge",
        headers=auth_headers(token),
        json={"email": "baecker@example.de", "password": "kunden-pw-123456", "name": "Herr Krause"},
    )
    assert create.status_code == 201
    slug = create.json()["login_slug"]
    assert slug

    link_resp = await client.get(f"/api/kundenportal/auth/link/{slug}")
    assert link_resp.status_code == 200
    body = link_resp.json()
    assert body["email"] == "baecker@example.de"
    assert body["kunde_name"] == "Bäckerei Krause"

    # Der Link allein loggt nicht ein -- ohne Passwort bleibt der Login-Endpunkt zustaendig.
    unknown = await client.get("/api/kundenportal/auth/link/does-not-exist")
    assert unknown.status_code == 404


# --- Rechte-Matrix ---------------------------------------------------------


@pytest.mark.asyncio
async def test_mitarbeiter_sieht_vorgaenge_aber_controller_kann_sie_nicht_anlegen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter", password="pw-123456")
    controller = await make_user(mandant=mandant, role="controller", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    mitarbeiter_token = await login(client, mitarbeiter.email, "pw-123456")
    controller_token = await login(client, controller.email, "pw-123456")

    # Default: mitarbeiter darf sehen+anlegen, controller nur sehen.
    liste = await client.get("/api/vorgaenge", headers=auth_headers(mitarbeiter_token))
    assert liste.status_code == 200

    create_mitarbeiter = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(mitarbeiter_token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Vorgang von Mitarbeiter",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert create_mitarbeiter.status_code == 201

    create_controller = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(controller_token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Vorgang von Controller",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert create_controller.status_code == 403


@pytest.mark.asyncio
async def test_mandant_admin_kann_rechte_matrix_fuer_controller_erweitern(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    controller = await make_user(mandant=mandant, role="controller", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    admin_token = await login(client, admin.email, "pw-123456")
    controller_token = await login(client, controller.email, "pw-123456")

    # Vorher: kein Bearbeiten-Recht fuer controller im Bereich vorgaenge.
    verboten = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(controller_token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Vorher verboten",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert verboten.status_code == 403

    setzen = await client.put(
        "/api/rechte-matrix",
        headers=auth_headers(admin_token),
        json={"rolle": "controller", "bereich": "vorgaenge", "aktion": "bearbeiten", "erlaubt": True},
    )
    assert setzen.status_code == 200
    eintrag = next(
        e for e in setzen.json() if e["rolle"] == "controller" and e["bereich"] == "vorgaenge" and e["aktion"] == "bearbeiten"
    )
    assert eintrag["erlaubt"] is True

    erlaubt = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(controller_token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Jetzt erlaubt",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert erlaubt.status_code == 201


@pytest.mark.asyncio
async def test_disponent_kann_rechte_matrix_nicht_aendern(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.get("/api/rechte-matrix", headers=auth_headers(token))
    assert resp.status_code == 403


# --- Zeiterfassung/Material-Sperre auf geschlossenem Vorgang ---------------


@pytest.mark.asyncio
async def test_zeiterfassung_start_auf_storniertem_vorgang_blockiert(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="storniert")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/start",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id)},
    )
    assert resp.status_code == 409
