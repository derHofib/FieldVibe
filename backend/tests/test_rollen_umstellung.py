"""Organigramm Schritt 6: Altlasten auf die Engine umgestellt -- disponent-Altlast,
Zeiterfassung nach Mitarbeiter-Scope, Nutzerliste nach Scope, fachliche
Rollenpruefungen (highlights/projekte/zeitplan/search, Empfaenger-Helfer)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import AuthContext
from app.api.routes import projekte as projekte_routes
from app.api.routes import search as search_routes
from app.api.routes import zeitplan as zeitplan_routes
from app.core import rollen
from app.db.session import system_session, tenant_session
from app.models.zeiterfassung import Zeiterfassung
from app.services import zuweisung_service as zs
from tests.conftest import auth_headers, login
from tests.test_scopes_daten import org  # noqa: F401  (Fixture)

PW = "pw-123456"


async def _kopf(client, user):
    return auth_headers(await login(client, user.email, PW))


# --- disponent-Altlast (kunden.py Einladungen, vorgaenge.py Partner-Zuweisung) ----


@pytest.mark.parametrize("rolle,erwartet", [("mandant_admin", 200), ("disponent", 200), ("controller", 403), ("techniker", 403)])
async def test_kunden_einladungen_liste_nach_recht(client, make_mandant, make_user, make_kunde, rolle, erwartet):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role=rolle, password=PW)
    kunde = await make_kunde(mandant=mandant)
    resp = await client.get(f"/api/kunden/{kunde.id}/einladungen", headers=await _kopf(client, user))
    assert resp.status_code == erwartet, resp.text


@pytest.mark.parametrize("rolle,erwartet", [("disponent", 404), ("controller", 403)])
async def test_kunden_einladung_widerrufen_und_erneut_senden_nach_recht(
    client, make_mandant, make_user, make_kunde, rolle, erwartet
):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role=rolle, password=PW)
    kunde = await make_kunde(mandant=mandant)
    kopf = await _kopf(client, user)
    pfad = f"/api/kunden/{kunde.id}/einladungen/{uuid.uuid4()}"
    # 404 = Gate passiert, Einladung existiert nicht; 403 = Gate greift.
    assert (await client.delete(pfad, headers=kopf)).status_code == erwartet
    assert (await client.post(f"{pfad}/erneut-senden", headers=kopf)).status_code == erwartet


async def test_kunden_einladungen_scope_ausserhalb_404(client, org):  # noqa: F811
    h = org["headers"]
    assert (await client.get(f"/api/kunden/{org['kunden']['a2']}/einladungen", headers=h["tla"])).status_code == 200
    assert (await client.get(f"/api/kunden/{org['kunden']['b1']}/einladungen", headers=h["tla"])).status_code == 404
    assert (await client.get(f"/api/kunden/{org['kunden']['b1']}/einladungen", headers=h["gf"])).status_code == 200


@pytest.mark.parametrize("rolle,erwartet", [("mandant_admin", 200), ("disponent", 200), ("controller", 403)])
async def test_partner_zuweisung_nach_recht(client, make_mandant, make_user, make_kunde, make_vorgang, rolle, erwartet):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role=rolle, password=PW)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}/partner-zuweisung",
        headers=await _kopf(client, user),
        json={"partner_id": None},
    )
    assert resp.status_code == erwartet, resp.text


async def test_partner_zuweisung_scope_ausserhalb_404(client, org):  # noqa: F811
    h = org["headers"]
    pfad = lambda key: f"/api/vorgaenge/{org['vorgaenge'][key]}/partner-zuweisung"  # noqa: E731
    assert (await client.patch(pfad("a2"), headers=h["tla"], json={"partner_id": None})).status_code == 200
    assert (await client.patch(pfad("b1"), headers=h["tla"], json={"partner_id": None})).status_code == 404


# --- Zeiterfassung nach Mitarbeiter-Scope ---------------------------------------


@pytest.fixture
async def zeiten(org):  # noqa: F811
    """Je ein Zeiteintrag fuer a1, a2, b1 an deren Vorgang."""
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    async with system_session() as session:
        for key in ("a1", "a2", "b1"):
            session.add(
                Zeiterfassung(
                    mandant_id=org["mandant"].id,
                    vorgang_id=org["vorgaenge"][key],
                    techniker_id=org["ids"][key],
                    start_at=start,
                    ende_at=start + timedelta(hours=1),
                    kategorie="auftrag",
                )
            )
        await session.flush()
    return org


async def _zeit_techniker(client, org, key, **params) -> set[uuid.UUID]:
    resp = await client.get("/api/zeiterfassung", headers=org["headers"][key], params=params)
    assert resp.status_code == 200, resp.text
    return {uuid.UUID(e["techniker_id"]) for e in resp.json()}


async def test_zeiterfassung_liste_teamleiter_teilbaum(client, zeiten):
    ids = zeiten["ids"]
    assert await _zeit_techniker(client, zeiten, "tla") == {ids["a1"], ids["a2"]}
    assert await _zeit_techniker(client, zeiten, "gf") == {ids["a1"], ids["a2"], ids["b1"]}
    assert await _zeit_techniker(client, zeiten, "bl") == {ids["a1"], ids["a2"], ids["b1"]}


async def test_zeiterfassung_techniker_filter_und_statistik_nach_scope(client, zeiten):
    h, ids = zeiten["headers"], zeiten["ids"]
    for pfad, param in (("", "techniker_id"), ("/statistik", "techniker_id")):
        url = f"/api/zeiterfassung{pfad}"
        assert (await client.get(url, headers=h["tla"], params={param: str(ids["a1"])})).status_code == 200
        assert (await client.get(url, headers=h["tla"], params={param: str(ids["b1"])})).status_code == 403
        assert (await client.get(url, headers=h["gf"], params={param: str(ids["b1"])})).status_code == 200
        # Eigene Daten immer, fremde mit Scope eigene nie.
        assert (await client.get(url, headers=h["a1"], params={param: str(ids["a1"])})).status_code == 200
        assert (await client.get(url, headers=h["a1"], params={param: str(ids["a2"])})).status_code == 403


async def test_zeiterfassung_wochenzettel_nach_scope(client, zeiten):
    h, ids = zeiten["headers"], zeiten["ids"]
    montag = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    url = "/api/zeiterfassung/wochenzettel-pdf"
    params = lambda key: {"woche_start": montag, "techniker_id": str(ids[key])}  # noqa: E731
    assert (await client.get(url, headers=h["tla"], params=params("a1"))).status_code == 200
    assert (await client.get(url, headers=h["tla"], params=params("b1"))).status_code == 403


async def test_zeiterfassung_csv_nach_scope(client, zeiten):
    h, ids = zeiten["headers"], zeiten["ids"]
    tla = await client.get("/api/zeiterfassung/export/csv", headers=h["tla"])
    assert tla.status_code == 200
    assert "Techniker A1" in tla.text and "Techniker A2" in tla.text and "Techniker B1" not in tla.text
    gf = await client.get("/api/zeiterfassung/export/csv", headers=h["gf"])
    assert "Techniker B1" in gf.text
    ausserhalb = await client.get(
        "/api/zeiterfassung/export/csv", headers=h["tla"], params={"techniker_id": str(ids["b1"])}
    )
    assert ausserhalb.status_code == 403


async def test_zeiterfassung_mandant_admin_und_ohne_recht_unveraendert(client, zeiten, make_user, make_kunde, make_vorgang):
    mandant = zeiten["mandant"]
    ids = zeiten["ids"]
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = await _kopf(client, admin)
    resp = await client.get("/api/zeiterfassung", headers=kopf)
    assert {uuid.UUID(e["techniker_id"]) for e in resp.json()} == {ids["a1"], ids["a2"], ids["b1"]}
    assert (await client.get("/api/zeiterfassung", headers=kopf, params={"techniker_id": str(ids["b1"])})).status_code == 200
    # Techniker-Legacy-Typ (nur sehen, kein mitarbeiterverwaltung.bearbeiten): fremde Personen weiter 403.
    techniker = await make_user(mandant=mandant, role="techniker", password=PW)
    kopf_t = await _kopf(client, techniker)
    assert (await client.get("/api/zeiterfassung", headers=kopf_t, params={"techniker_id": str(ids["a1"])})).status_code == 403
    assert (await client.get("/api/zeiterfassung", headers=kopf_t, params={"techniker_id": str(techniker.id)})).status_code == 200


async def test_zeiterfassung_start_nur_zugewiesene_kunden_ueber_scope(client, org):  # noqa: F811
    h = org["headers"]
    # a1: kunden Scope eigene -> nur Kunde a1, Vorgang b1 ist fremd (403 wie bisher).
    resp = await client.post("/api/zeiterfassung/start", headers=h["a1"], json={"vorgang_id": str(org["vorgaenge"]["b1"])})
    assert resp.status_code == 403
    resp = await client.post("/api/zeiterfassung/start", headers=h["a1"], json={"vorgang_id": str(org["vorgaenge"]["a1"])})
    assert resp.status_code == 201, resp.text


# --- Nutzerliste nach Scope -------------------------------------------------------


async def _namen(client, org, key, pfad="/api/users") -> set[str]:
    resp = await client.get(pfad, headers=org["headers"][key])
    assert resp.status_code == 200, resp.text
    return {u["name"] for u in resp.json()}


async def test_nutzerliste_nach_scope(client, org, make_user):  # noqa: F811
    assert await _namen(client, org, "a1") == {"Techniker A1"}  # eigene
    assert await _namen(client, org, "tla") == {"Teamleiter A", "Techniker A1", "Techniker A2", "Teamkraft A"}  # teilbaum
    alle = {n for n in await _namen(client, org, "gf")}  # mandant
    assert {"Techniker B1", "Teamleiter B", "QM"} <= alle
    admin = await make_user(mandant=org["mandant"], role="mandant_admin", password=PW)
    resp = await client.get("/api/users", headers=await _kopf(client, admin))
    assert {u["name"] for u in resp.json()} >= alle


async def test_nutzer_auswahl_mandantenweit_ohne_email(client, org):  # noqa: F811
    gf_liste = await _namen(client, org, "gf")
    assert await _namen(client, org, "a1", "/api/users/auswahl") >= gf_liste
    resp = await client.get("/api/users/auswahl", headers=org["headers"]["tla"])
    assert resp.status_code == 200
    assert all("email" not in u and "mandant_id" not in u for u in resp.json())
    assert {"Techniker B1", "Techniker A1"} <= {u["name"] for u in resp.json()}


async def test_nutzer_auswahl_ohne_recht_403(client, make_mandant, make_user):
    mandant = await make_mandant()
    # Technik-Typ ohne mitarbeiterverwaltung.sehen: "mitarbeiter" hat nur bearbeiten.
    user = await make_user(mandant=mandant, role="mitarbeiter", password=PW)
    kopf = await _kopf(client, user)
    assert (await client.get("/api/users/auswahl", headers=kopf)).status_code == 403
    assert (await client.get("/api/users", headers=kopf)).status_code == 403


# --- fachliche Rollenpruefungen ueber die Engine ---------------------------------


async def test_highlight_loeschen_alle_mit_vorgaenge_loeschen_recht(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    # Bestehende Tests decken mandant_admin und Techniker ab; hier custom MIT Recht.
    from tests.test_highlights import _make_foto_event

    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password=PW)
    disponent = await make_user(mandant=mandant, role="disponent", password=PW)  # vorgaenge.loeschen
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    event = await _make_foto_event(mandant, vorgang)
    erstellt = await client.post(
        "/api/highlights", headers=await _kopf(client, techniker), json={"vorgang_event_id": event.id}
    )
    resp = await client.delete(f"/api/highlights/{erstellt.json()['id']}", headers=await _kopf(client, disponent))
    assert resp.status_code == 204, resp.text


async def test_rechte_helfer_der_routen_nutzen_engine(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    disponent = await make_user(mandant=mandant, role="disponent")
    techniker = await make_user(mandant=mandant, role="techniker")

    def ctx(user):
        return AuthContext(user_id=user.id, mandant_id=mandant.id, role=user.role, account_typ_id=user.account_typ_id)

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        # projekte.py: _hat_projekte_recht
        assert await projekte_routes._hat_projekte_recht(session, ctx(admin), "bearbeiten")
        assert not await projekte_routes._hat_projekte_recht(session, ctx(disponent), "bearbeiten")
        # zeitplan.py
        assert await zeitplan_routes._darf_projekte_sehen(session, ctx(admin))
        assert not await zeitplan_routes._darf_projekte_sehen(session, ctx(techniker))
        assert await zeitplan_routes._darf_bearbeiten(session, ctx(admin))
        assert not await zeitplan_routes._darf_bearbeiten(session, ctx(techniker))
        pruefer = zeitplan_routes._recht_eines_von(("projekte", "zeitplan_sehen"))
        assert (await pruefer(auth=ctx(techniker), session=session)).user_id == techniker.id
        assert (await pruefer(auth=ctx(admin), session=session)).user_id == admin.id
        # search.py: Rechnungstreffer nur mit abrechnung.sehen (Disponent ja, Techniker hat nur sehen -> ja; Mitarbeiter nein)
        mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter")
        assert await search_routes._darf_rechnungen_sehen(session, ctx(admin))
        assert await search_routes._darf_rechnungen_sehen(session, ctx(disponent))
        assert not await search_routes._darf_rechnungen_sehen(session, ctx(mitarbeiter))


async def test_verantwortliche_und_technik_ids_ueber_engine(client, org, make_user):  # noqa: F811
    mandant, ids = org["mandant"], org["ids"]
    admin = await make_user(mandant=mandant, role="mandant_admin")
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        dispo = await zs.dispo_verantwortliche_user_ids(session, mandant.id)
        abrechnung = await zs.abrechnung_verantwortliche_user_ids(session, mandant.id)
        technik = await zs.technik_user_ids(session, mandant.id)
    # Positions-Besetzte ohne users.account_typ_id zaehlen mit (Engine, nicht Altpfad).
    assert {admin.id, ids["gf"], ids["tla"]} <= dispo
    # Der Test-Organigramm-Typ vergibt dispo, aber nicht abrechnung.
    assert admin.id in abrechnung and ids["tla"] not in abrechnung
    # Zuweisbare "Techniker" = kunden.sehen nur mit Scope eigene.
    assert {ids["a1"], ids["a2"], ids["b1"]} <= technik
    assert not ({ids["gf"], ids["tla"], admin.id} & technik)


def test_rollen_helfer():
    class K:
        def __init__(self, role):
            self.role = role

    assert rollen.ist_plattform_admin(K("super_admin")) and not rollen.ist_plattform_admin(K("mandant_admin"))
    assert rollen.ist_mandant_admin(K("mandant_admin")) and not rollen.ist_mandant_admin(K("loesch_operativ"))
    assert rollen.hat_admin_rechte_im_mandant(K("loesch_operativ")) and not rollen.hat_admin_rechte_im_mandant(K("custom"))
    assert rollen.ist_mitarbeiter_account(K("custom")) and not rollen.ist_mitarbeiter_account(K("loesch_ansicht"))
