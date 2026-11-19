"""Kundenbetreuung: Betreuer/Hauptbetreuer an kunde_zuweisungen, Sammelaktionen,
automatische Zuweisung neuer Vorgaenge an den Hauptbetreuer."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.vorgang import Vorgang
from app.models.vorgang_anfrage import VorgangAnfrage
from app.models.vorgang_event import VorgangEvent
from app.services.scheduler_service import run_dauerauftraege_scheduler, run_pruefzyklen_scheduler
from tests.conftest import auth_headers, login
from tests.mcp_helfer import PASSWORT, custom_nutzer
from tests.test_dauerauftraege import _make_dauerauftrag_mit_ziel
from tests.test_scheduler import _make_pruefzyklus
from tests.test_standorte_anfragen_rechte import _make_zugang

PW = "pw-123456"


async def _admin(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    return mandant, admin


def _put(client, token, kunde, user_ids, haupt=None):
    return client.put(
        f"/api/kunden/{kunde.id}/betreuung",
        headers=auth_headers(token),
        json={"user_ids": [str(u.id) for u in user_ids], "hauptbetreuer_id": str(haupt.id) if haupt else None},
    )


async def _zuweisungen(kunde_id):
    async with system_session(grund="test") as session:
        zeilen = await session.execute(select(KundeZuweisung).where(KundeZuweisung.kunde_id == kunde_id))
        return {z.user_id: z.hauptbetreuer for z in zeilen.scalars().all()}


@pytest.mark.asyncio
async def test_mitarbeiter_ohne_einschraenkung_ist_zuweisbar_und_hauptbetreuer(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin = await _admin(make_mandant, make_user)
    dispo = await make_user(mandant=mandant, role="disponent", name="Dora Dispo")
    tech = await make_user(mandant=mandant, role="techniker", name="Tim Tech")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)

    resp = await _put(client, token, kunde, [dispo, tech], haupt=dispo)
    assert resp.status_code == 200, resp.text
    zeilen = resp.json()
    assert [z["user_id"] for z in zeilen] == [str(dispo.id), str(tech.id)]
    assert [z["hauptbetreuer"] for z in zeilen] == [True, False]
    assert [z["nur_betreute_kunden"] for z in zeilen] == [False, True]
    assert zeilen[0]["account_typ_name"] is not None

    get = await client.get(f"/api/kunden/{kunde.id}/betreuung", headers=auth_headers(token))
    assert get.json() == zeilen
    profil = await client.get(f"/api/kunden/{kunde.id}/profil", headers=auth_headers(token))
    assert profil.json()["betreuung"] == zeilen
    assert {t["id"] for t in profil.json()["techniker"]} == {str(dispo.id), str(tech.id)}


@pytest.mark.asyncio
async def test_nur_ein_hauptbetreuer(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    a = await make_user(mandant=mandant, role="disponent", name="A")
    b = await make_user(mandant=mandant, role="techniker", name="B")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)

    assert (await _put(client, token, kunde, [a], haupt=b)).status_code == 400

    assert (await _put(client, token, kunde, [a, b], haupt=a)).status_code == 200
    assert (await _put(client, token, kunde, [a, b], haupt=b)).status_code == 200
    assert await _zuweisungen(kunde.id) == {a.id: False, b.id: True}

    # Ohne Hauptbetreuer: alle Flags weg.
    assert (await _put(client, token, kunde, [a, b], haupt=None)).status_code == 200
    assert await _zuweisungen(kunde.id) == {a.id: False, b.id: False}

    # Der partielle Unique-Index laesst auch direkt in der DB keinen zweiten zu.
    await _put(client, token, kunde, [a, b], haupt=a)
    async with system_session(grund="test") as session:
        zeile_b = (
            await session.execute(
                select(KundeZuweisung).where(KundeZuweisung.kunde_id == kunde.id, KundeZuweisung.user_id == b.id)
            )
        ).scalar_one()
        zeile_b.hauptbetreuer = True
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_put_betreuung_lehnt_ungueltige_nutzer_ab(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    fremd_mandant = await make_mandant(name="Fremdbetrieb")
    fremd = await make_user(mandant=fremd_mandant, role="techniker")
    inaktiv = await make_user(mandant=mandant, role="techniker", aktiv=False)
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)

    assert (await _put(client, token, kunde, [fremd])).status_code == 400
    assert (await _put(client, token, kunde, [inaktiv])).status_code == 400


@pytest.mark.asyncio
async def test_portalzugang_ist_kein_betreuer(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant)
    zugang = await _make_zugang(mandant, kunde)
    token = await login(client, admin.email, PW)

    resp = await client.put(
        f"/api/kunden/{kunde.id}/betreuung",
        headers=auth_headers(token),
        json={"user_ids": [str(zugang.id)]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_haupt_bleibt_bei_put_techniker_erhalten(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    a = await make_user(mandant=mandant, role="disponent", name="A")
    b = await make_user(mandant=mandant, role="techniker", name="B")
    c = await make_user(mandant=mandant, role="techniker", name="C")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [a, b], haupt=a)

    resp = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(token),
        json={"user_ids": [str(a.id), str(c.id)]},
    )
    assert resp.status_code == 200
    assert await _zuweisungen(kunde.id) == {a.id: True, c.id: False}

    # Faellt der Hauptbetreuer weg, gibt es keinen mehr.
    await client.put(
        f"/api/kunden/{kunde.id}/techniker", headers=auth_headers(token), json={"user_ids": [str(c.id)]}
    )
    assert await _zuweisungen(kunde.id) == {c.id: False}


@pytest.mark.asyncio
async def test_eingeschraenkter_nutzer_verliert_zugriff_nach_entfernen(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin = await _admin(make_mandant, make_user)
    tech = await make_user(mandant=mandant, role="techniker", password=PW)
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)
    tech_token = await login(client, tech.email, PW)

    await _put(client, token, kunde, [tech], haupt=tech)
    assert (await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(tech_token))).status_code == 200
    await _put(client, token, kunde, [])
    assert (await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(tech_token))).status_code == 404


@pytest.mark.asyncio
async def test_kundenliste_liefert_betreuung_hauptbetreuer_zuerst(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin = await _admin(make_mandant, make_user)
    anna = await make_user(mandant=mandant, role="disponent", name="Anna")
    zora = await make_user(mandant=mandant, role="techniker", name="Zora")
    kunde = await make_kunde(mandant=mandant, name="Mit Betreuung")
    ohne = await make_kunde(mandant=mandant, name="Ohne Betreuung")
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [anna, zora], haupt=zora)

    resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert resp.status_code == 200
    je_id = {k["id"]: k["betreuung"] for k in resp.json()}
    assert je_id[str(ohne.id)] == []
    assert je_id[str(kunde.id)] == [
        {"user_id": str(zora.id), "name": "Zora", "hauptbetreuer": True},
        {"user_id": str(anna.id), "name": "Anna", "hauptbetreuer": False},
    ]


@pytest.mark.asyncio
async def test_audit_eintrag_bei_aenderung(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    a = await make_user(mandant=mandant, role="techniker")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [a], haupt=a)
    await _put(client, token, kunde, [a], haupt=a)  # unveraendert: kein zweiter Eintrag

    async with system_session(grund="test") as session:
        eintraege = (
            await session.execute(select(AuditLog).where(AuditLog.aktion == "kunde.betreuung_geaendert"))
        ).scalars().all()
    assert len(eintraege) == 1
    nutzlast = eintraege[0].payload
    assert nutzlast["vorher"] == {"user_ids": [], "hauptbetreuer_id": None}
    assert nutzlast["nachher"] == {"user_ids": [str(a.id)], "hauptbetreuer_id": str(a.id)}


# --- Sammelaktionen -----------------------------------------------------------------


def _sammel(client, token, kunden, aktion, user, **extra):
    return client.post(
        "/api/kunden/betreuung/sammel",
        headers=auth_headers(token),
        json={"kunde_ids": [str(k.id) for k in kunden], "aktion": aktion, "user_id": str(user.id), **extra},
    )


@pytest.mark.asyncio
async def test_sammel_hinzufuegen_hauptbetreuer_entfernen(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    a = await make_user(mandant=mandant, role="disponent", name="A")
    b = await make_user(mandant=mandant, role="techniker", name="B")
    k1, k2, k3 = [await make_kunde(mandant=mandant, name=f"K{i}") for i in range(3)]
    token = await login(client, admin.email, PW)
    await _put(client, token, k1, [a], haupt=a)
    await _put(client, token, k2, [b], haupt=b)

    # hinzufuegen: k1 hat a schon (geaendert=0 fuer a), k2/k3 neu.
    resp = await _sammel(client, token, [k1, k2, k3], "hinzufuegen", a)
    assert resp.json() == {"geaendert": 2}
    assert await _zuweisungen(k1.id) == {a.id: True}
    assert await _zuweisungen(k2.id) == {b.id: True, a.id: False}
    assert await _zuweisungen(k3.id) == {a.id: False}

    # mit auch_hauptbetreuer nur dort Haupt, wo keiner existiert (k3); k1 hat a schon als Haupt.
    resp = await _sammel(client, token, [k1, k2, k3], "hinzufuegen", a, auch_hauptbetreuer=True)
    assert resp.json() == {"geaendert": 1}
    assert await _zuweisungen(k2.id) == {b.id: True, a.id: False}
    assert await _zuweisungen(k3.id) == {a.id: True}

    # hauptbetreuer: k2 hat b schon als Haupt (unveraendert), bei k1/k3 loest b den Haupt a ab.
    resp = await _sammel(client, token, [k1, k2, k3], "hauptbetreuer", b)
    assert resp.json() == {"geaendert": 2}
    assert await _zuweisungen(k1.id) == {a.id: False, b.id: True}
    assert await _zuweisungen(k2.id) == {b.id: True, a.id: False}
    assert await _zuweisungen(k3.id) == {a.id: False, b.id: True}

    resp = await _sammel(client, token, [k1, k2, k3], "entfernen", b)
    assert resp.json() == {"geaendert": 3}
    assert await _zuweisungen(k2.id) == {a.id: False}
    resp = await _sammel(client, token, [k1, k2, k3], "entfernen", b)
    assert resp.json() == {"geaendert": 0}

    async with system_session(grund="test") as session:
        anzahl = len(
            (await session.execute(select(AuditLog).where(AuditLog.aktion == "kunde.betreuung_geaendert")))
            .scalars()
            .all()
        )
    # 2 PUTs, dann Sammel: 2 + 1 + 2 + 3 geaenderte Kunden
    assert anzahl == 2 + 2 + 1 + 2 + 3


@pytest.mark.asyncio
async def test_sammel_ausserhalb_scope_oder_fremder_mandant_404_ohne_teilaenderung(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin = await _admin(make_mandant, make_user)
    fremd_mandant = await make_mandant(name="Fremdbetrieb")
    ziel = await make_user(mandant=mandant, role="techniker", name="Ziel")
    eigener = await custom_nutzer(
        mandant,
        "Eingeschraenkt",
        {"kunden": ("sehen", "bearbeiten")},
        scopes_je_bereich={"kunden": "eigene"},
    )
    k_eigen = await make_kunde(mandant=mandant, name="Eigen")
    k_fremd = await make_kunde(mandant=mandant, name="Nicht meiner")
    k_anderer_mandant = await make_kunde(mandant=fremd_mandant, name="Anderer Mandant")
    admin_token = await login(client, admin.email, PW)
    await _put(client, admin_token, k_eigen, [eigener])

    token = await login(client, eigener.email, PASSWORT)

    resp = await _sammel(client, token, [k_eigen, k_fremd], "hinzufuegen", ziel)
    assert resp.status_code == 404
    assert await _zuweisungen(k_fremd.id) == {}
    assert ziel.id not in await _zuweisungen(k_eigen.id)

    resp = await _sammel(client, admin_token, [k_eigen, k_anderer_mandant], "hinzufuegen", ziel)
    assert resp.status_code == 404
    assert ziel.id not in await _zuweisungen(k_eigen.id)

    # Im Scope funktioniert es.
    assert (await _sammel(client, token, [k_eigen], "hinzufuegen", ziel)).json() == {"geaendert": 1}


@pytest.mark.asyncio
async def test_sammel_validiert_nutzer_und_body(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    fremd = await make_user(mandant=await make_mandant(name="Fremdbetrieb"), role="techniker")
    inaktiv = await make_user(mandant=mandant, role="techniker", aktiv=False)
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, PW)

    assert (await _sammel(client, token, [kunde], "hinzufuegen", fremd)).status_code == 400
    assert (await _sammel(client, token, [kunde], "hauptbetreuer", inaktiv)).status_code == 400
    leer = await client.post(
        "/api/kunden/betreuung/sammel",
        headers=auth_headers(token),
        json={"kunde_ids": [], "aktion": "hinzufuegen", "user_id": str(admin.id)},
    )
    assert leer.status_code == 422


# --- Automatische Zuweisung an den Hauptbetreuer ----------------------------------


async def _vorgang_events(vorgang_id):
    async with system_session(grund="test") as session:
        return [
            e.body
            for e in (
                await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang_id))
            ).scalars()
        ]


@pytest.mark.asyncio
async def test_neuer_vorgang_bekommt_hauptbetreuer(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    haupt = await make_user(mandant=mandant, role="disponent", name="Haupt Betreuer")
    kunde = await make_kunde(mandant=mandant)
    ohne_kunde_haupt = await make_kunde(mandant=mandant, name="Ohne Haupt")
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [haupt], haupt=haupt)

    def neu(k, **extra):
        return client.post(
            "/api/vorgaenge",
            headers=auth_headers(token),
            json={"kunde_id": str(k.id), "titel": "T", "abrechnungsart": "aufwand", "leistungstyp": "stoerung", **extra},
        )

    resp = await neu(kunde)
    assert resp.status_code == 201
    assert resp.json()["zugewiesener_user_id"] == str(haupt.id)
    assert "Zugewiesen an: Haupt Betreuer (Hauptbetreuer des Kunden)" in await _vorgang_events(resp.json()["id"])

    # Dedupe-Treffer (client_uuid) aendert nichts und legt nichts neu an.
    import uuid

    cu = str(uuid.uuid4())
    erst = await neu(kunde, client_uuid=cu)
    zweit = await neu(kunde, client_uuid=cu)
    assert (erst.status_code, zweit.status_code) == (201, 200)
    assert len([e for e in await _vorgang_events(erst.json()["id"]) if e.startswith("Zugewiesen")]) == 1

    assert (await neu(ohne_kunde_haupt)).json()["zugewiesener_user_id"] is None

    # Deaktivierter Hauptbetreuer bekommt nichts mehr.
    async with system_session(grund="test") as session:
        user = await session.get(type(haupt), haupt.id)
        user.aktiv = False
    assert (await neu(kunde)).json()["zugewiesener_user_id"] is None


@pytest.mark.asyncio
async def test_scheduler_vorgaenge_bekommen_hauptbetreuer(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant, admin = await _admin(make_mandant, make_user)
    haupt = await make_user(mandant=mandant, role="techniker", name="Haupt")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [haupt], haupt=haupt)

    await _make_pruefzyklus(mandant, anlage)
    await _make_dauerauftrag_mit_ziel(
        mandant=mandant, kunde=kunde, naechste_faelligkeit_am=date.today() - timedelta(days=1)
    )
    assert (await run_pruefzyklen_scheduler([mandant.id]))["vorgaenge_erstellt"] == 1
    assert (await run_dauerauftraege_scheduler([mandant.id]))["vorgaenge_erstellt"] == 1

    async with system_session(grund="test") as session:
        vorgaenge = (await session.execute(select(Vorgang).where(Vorgang.kunde_id == kunde.id))).scalars().all()
    assert len(vorgaenge) == 2
    assert {v.zugewiesener_user_id for v in vorgaenge} == {haupt.id}


@pytest.mark.asyncio
async def test_portal_anfrage_annehmen_weist_hauptbetreuer_zu(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    haupt = await make_user(mandant=mandant, role="techniker", name="Haupt")
    kunde = await make_kunde(mandant=mandant)
    zugang = await _make_zugang(mandant, kunde)
    token = await login(client, admin.email, PW)
    await _put(client, token, kunde, [haupt], haupt=haupt)
    async with system_session(grund="test") as session:
        anfrage = VorgangAnfrage(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            kundenportal_zugang_id=zugang.id,
            titel="Defekt",
            leistungstyp="stoerung",
        )
        session.add(anfrage)
        await session.flush()
        anfrage_id = anfrage.id

    resp = await client.post(
        f"/api/vorgang-anfragen/{anfrage_id}/annehmen",
        headers=auth_headers(token),
        json={"abrechnungsart": "aufwand"},
    )
    assert resp.status_code == 200
    vorgang = await client.get(f"/api/vorgaenge/{resp.json()['vorgang_id']}", headers=auth_headers(token))
    assert vorgang.json()["zugewiesener_user_id"] == str(haupt.id)


@pytest.mark.asyncio
async def test_betreuer_auswahl_ohne_mitarbeiterverwaltung(client, make_mandant, make_user, make_kunde):
    mandant, admin = await _admin(make_mandant, make_user)
    pfleger = await custom_nutzer(mandant, "Pfleger", {"kunden": ("sehen", "bearbeiten")})
    aktiv = await make_user(mandant=mandant, role="techniker", name="Aktiv")
    inaktiv_betreuer = await make_user(mandant=mandant, role="techniker", name="Inaktiv Betreuer")
    inaktiv_frei = await make_user(mandant=mandant, role="techniker", name="Inaktiv Frei")
    fremd = await make_user(mandant=await make_mandant(name="Fremdbetrieb"), role="techniker", name="Fremd")
    kunde = await make_kunde(mandant=mandant)
    admin_token = await login(client, admin.email, PW)
    await _put(client, admin_token, kunde, [aktiv, inaktiv_betreuer], haupt=aktiv)
    async with system_session(grund="test") as session:
        for u in (inaktiv_betreuer, inaktiv_frei):
            (await session.get(type(u), u.id)).aktiv = False

    token = await login(client, pfleger.email, PASSWORT)
    resp = await client.get("/api/kunden/betreuer-auswahl", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    je_name = {r["name"]: r for r in resp.json()}
    assert "Inaktiv Frei" not in je_name and "Fremd" not in je_name
    assert je_name["Aktiv"]["anzahl_kunden"] == 1 and je_name["Aktiv"]["nur_betreute_kunden"] is True
    assert je_name["Inaktiv Betreuer"]["aktiv"] is False
    assert je_name["Pfleger"]["anzahl_kunden"] == 0
    assert [r["name"] for r in resp.json()] == sorted(je_name)

    ohne_recht = await custom_nutzer(mandant, "Leser", {"kunden": ("sehen",)})
    t2 = await login(client, ohne_recht.email, PASSWORT)
    assert (await client.get("/api/kunden/betreuer-auswahl", headers=auth_headers(t2))).status_code == 403
