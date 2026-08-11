"""Tests fuer die Rechnungsuebersicht: Filter, Sortierung, Pagination,
Summenzeile, CSV-Export und die Sichtbarkeit von Rechnungen in der globalen
Suche."""
import uuid
from datetime import date, timedelta

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.user import User
from tests.conftest import auth_headers, login


async def _make_custom_account_typ_ohne_abrechnung(mandant) -> AccountTyp:
    """Ein Account-Typ ohne 'abrechnung:sehen' -- Vorbild:
    test_formulare.py::_make_custom_mit_formulare_recht. Es gibt keine
    generische make_account_typ-Fixture in conftest.py, deshalb direkt ueber
    system_session wie dort."""
    async with system_session() as session:
        account_typ = AccountTyp(mandant_id=mandant.id, name=f"Ohne-Abrechnung-{uuid.uuid4().hex[:6]}")
        session.add(account_typ)
        await session.flush()
        session.add(
            AccountTypRecht(account_typ_id=account_typ.id, bereich="vorgaenge", aktion="sehen", erlaubt=True)
        )
        await session.flush()
        await session.refresh(account_typ)
        return account_typ


async def _make_custom_user(mandant, account_typ) -> User:
    password = "hunter2!!"
    async with system_session() as session:
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password(password),
            role="custom",
            account_typ_id=account_typ.id,
            name="Rechte-Tester",
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        user._plaintext_password = password
        return user


async def _anlegen(client, token, kunde_id, *, netto, faellig=None, versenden=False, bezahlen=False):
    payload = {"kunde_id": str(kunde_id), "betrag_netto": str(netto)}
    if faellig:
        payload["faellig_am"] = faellig.isoformat()
    resp = await client.post("/api/rechnungen", headers=auth_headers(token), json=payload)
    assert resp.status_code == 201
    rechnung = resp.json()
    if versenden or bezahlen:
        await client.patch(
            f"/api/rechnungen/{rechnung['id']}",
            headers=auth_headers(token),
            json={"status": "versendet"},
        )
    if bezahlen:
        await client.patch(
            f"/api/rechnungen/{rechnung['id']}",
            headers=auth_headers(token),
            json={"status": "bezahlt"},
        )
    return rechnung


@pytest.fixture
async def uebersicht_daten(client, make_mandant, make_user, make_kunde):
    """Vier Rechnungen mit unterschiedlichen Zustaenden, die alle Filter
    unterscheidbar machen -- eine davon absichtlich MIT Positionen, damit der
    coalesce-Zweig von netto_sql() (Positionen statt betrag_netto) mitgetestet
    wird."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant, name="Alpha Bau GmbH")
    kunde_b = await make_kunde(mandant=mandant, name="Beta Handel KG")
    token = await login(client, admin.email, "pw-123456")

    gestern = date.today() - timedelta(days=10)
    morgen = date.today() + timedelta(days=10)

    entwurf = await _anlegen(client, token, kunde_a.id, netto=100, faellig=morgen)
    ueberfaellig = await _anlegen(client, token, kunde_b.id, netto=2000, faellig=gestern, versenden=True)
    offen = await _anlegen(client, token, kunde_a.id, netto=500, faellig=morgen, versenden=True)
    bezahlt = await _anlegen(client, token, kunde_b.id, netto=750, faellig=morgen, bezahlen=True)

    # Rechnung mit eigenen Positionen: Netto ergibt sich aus 4 * 25 = 100,
    # nicht aus dem uebergebenen betrag_netto (0).
    mit_positionen = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde_a.id),
            "betrag_netto": "0",
            "positionen": [{"beschreibung": "Kabel", "menge": "4", "einzelpreis": "25.00"}],
        },
    )
    assert mit_positionen.status_code == 201

    return {
        "token": token,
        "kunde_a": kunde_a,
        "kunde_b": kunde_b,
        "entwurf": entwurf,
        "ueberfaellig": ueberfaellig,
        "offen": offen,
        "bezahlt": bezahlt,
        "mit_positionen": mit_positionen.json(),
    }


@pytest.mark.asyncio
async def test_uebersicht_liefert_envelope_mit_summen(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    resp = await client.get("/api/rechnungen", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    assert body["gesamt_anzahl"] == 5
    # 100 + 2000 + 500 + 750 + 100 (aus Positionen) = 3450
    assert body["summe_netto"] == "3450.00"
    assert body["summe_brutto"] == "4105.50"


@pytest.mark.asyncio
async def test_summen_gelten_fuer_gesamtmenge_nicht_nur_fuer_die_seite(client, uebersicht_daten):
    """Eine Summenzeile, die nur die ausgelieferten Zeilen addiert, waere
    irrefuehrend -- deshalb sind die Summen bewusst limit-unabhaengig."""
    token = uebersicht_daten["token"]
    ganz = (await client.get("/api/rechnungen", headers=auth_headers(token))).json()
    seite = (await client.get("/api/rechnungen?limit=2", headers=auth_headers(token))).json()

    assert len(seite["eintraege"]) == 2
    assert seite["gesamt_anzahl"] == ganz["gesamt_anzahl"] == 5
    assert seite["summe_brutto"] == ganz["summe_brutto"]


@pytest.mark.asyncio
async def test_freitext_trifft_rechnungsnummer_und_kundenname(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    nummer = uebersicht_daten["ueberfaellig"]["rechnungsnummer"]

    per_nummer = (
        await client.get(f"/api/rechnungen?q={nummer}", headers=auth_headers(token))
    ).json()
    assert [e["rechnungsnummer"] for e in per_nummer["eintraege"]] == [nummer]

    per_kunde = (await client.get("/api/rechnungen?q=Beta", headers=auth_headers(token))).json()
    kunde_b_id = str(uebersicht_daten["kunde_b"].id)
    assert per_kunde["gesamt_anzahl"] == 2
    assert all(e["kunde_id"] == kunde_b_id for e in per_kunde["eintraege"])


@pytest.mark.asyncio
async def test_nur_offen_schliesst_bezahlte_aus(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    body = (await client.get("/api/rechnungen?nur_offen=1", headers=auth_headers(token))).json()
    assert "bezahlt" not in {e["status"] for e in body["eintraege"]}
    assert body["summe_offen"] == body["summe_brutto"]


@pytest.mark.asyncio
async def test_nur_ueberfaellig_ignoriert_entwuerfe(client, uebersicht_daten, make_kunde):
    """Ein Entwurf mit vergangener Faelligkeit ist NICHT ueberfaellig -- er hat
    den Kunden nie erreicht. Der SQL-Filter muss deckungsgleich mit dem
    berechneten Feld ist_ueberfaellig sein."""
    token = uebersicht_daten["token"]
    await _anlegen(
        client,
        token,
        uebersicht_daten["kunde_a"].id,
        netto=99,
        faellig=date.today() - timedelta(days=30),
    )

    body = (
        await client.get("/api/rechnungen?nur_ueberfaellig=1", headers=auth_headers(token))
    ).json()
    assert body["gesamt_anzahl"] == 1
    eintrag = body["eintraege"][0]
    assert eintrag["rechnungsnummer"] == uebersicht_daten["ueberfaellig"]["rechnungsnummer"]
    assert eintrag["ist_ueberfaellig"] is True
    assert eintrag["tage_ueberfaellig"] == 10
    assert all(e["ist_ueberfaellig"] for e in body["eintraege"])


@pytest.mark.asyncio
async def test_mehrfacher_statusfilter(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    body = (
        await client.get(
            "/api/rechnungen?status=versendet&status=bezahlt", headers=auth_headers(token)
        )
    ).json()
    assert {e["status"] for e in body["eintraege"]} == {"versendet", "bezahlt"}
    assert body["gesamt_anzahl"] == 3


@pytest.mark.asyncio
async def test_betragsfilter_rechnet_auf_brutto_auch_bei_positionen(client, uebersicht_daten):
    """betrag_von/bis filtern auf Brutto, das nirgends persistiert ist. Die
    Rechnung mit Positionen (Netto 100 -> Brutto 119) muss dabei genauso
    beruecksichtigt werden wie eine mit betrag_netto."""
    token = uebersicht_daten["token"]
    body = (
        await client.get("/api/rechnungen?betrag_bis=200", headers=auth_headers(token))
    ).json()
    bruttos = sorted(e["betrag_brutto"] for e in body["eintraege"])
    assert bruttos == ["119.00", "119.00"]


@pytest.mark.asyncio
async def test_sortierung_nach_betrag(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    aufsteigend = (
        await client.get("/api/rechnungen?sort=betrag", headers=auth_headers(token))
    ).json()
    werte = [float(e["betrag_brutto"]) for e in aufsteigend["eintraege"]]
    assert werte == sorted(werte)

    absteigend = (
        await client.get("/api/rechnungen?sort=-betrag", headers=auth_headers(token))
    ).json()
    assert [float(e["betrag_brutto"]) for e in absteigend["eintraege"]] == sorted(werte, reverse=True)


@pytest.mark.asyncio
async def test_pagination_ist_ueber_seitengrenze_stabil(client, uebersicht_daten):
    """Ohne Tiebreaker auf Rechnung.id koennten bei gleichen Sortierwerten
    Zeilen doppelt erscheinen oder durchfallen."""
    token = uebersicht_daten["token"]
    seite1 = (
        await client.get("/api/rechnungen?sort=nummer&limit=2&offset=0", headers=auth_headers(token))
    ).json()
    seite2 = (
        await client.get("/api/rechnungen?sort=nummer&limit=2&offset=2", headers=auth_headers(token))
    ).json()
    seite3 = (
        await client.get("/api/rechnungen?sort=nummer&limit=2&offset=4", headers=auth_headers(token))
    ).json()

    alle = [e["id"] for e in seite1["eintraege"] + seite2["eintraege"] + seite3["eintraege"]]
    assert len(alle) == 5
    assert len(set(alle)) == 5


@pytest.mark.asyncio
async def test_unbekannter_sortierschluessel_wird_abgelehnt(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    resp = await client.get("/api/rechnungen?sort=quatsch", headers=auth_headers(token))
    assert resp.status_code == 400
    assert "Sortierschlüssel" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_csv_export_kollidiert_nicht_mit_der_uuid_route(client, uebersicht_daten):
    """/export/csv muss vor /{rechnung_id} deklariert sein, sonst versucht
    FastAPI "export" als UUID zu parsen und antwortet 422."""
    token = uebersicht_daten["token"]
    resp = await client.get("/api/rechnungen/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")

    text = resp.content.decode("utf-8-sig")
    kopf = text.splitlines()[0]
    assert kopf.split(";")[0] == "Rechnungsnummer"
    assert "Tage überfällig" in kopf
    # Kopfzeile + 5 Rechnungen
    assert len([z for z in text.splitlines() if z.strip()]) == 6


@pytest.mark.asyncio
async def test_csv_export_beruecksichtigt_die_filter(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    resp = await client.get(
        "/api/rechnungen/export/csv?nur_ueberfaellig=1", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    zeilen = [z for z in resp.content.decode("utf-8-sig").splitlines() if z.strip()]
    assert len(zeilen) == 2
    assert uebersicht_daten["ueberfaellig"]["rechnungsnummer"] in zeilen[1]


@pytest.mark.asyncio
async def test_rechnung_wird_in_globaler_suche_gefunden(client, uebersicht_daten):
    token = uebersicht_daten["token"]
    nummer = uebersicht_daten["ueberfaellig"]["rechnungsnummer"]
    resp = await client.get(f"/api/search?q={nummer}", headers=auth_headers(token))
    assert resp.status_code == 200

    rechnungstreffer = [t for t in resp.json()["treffer"] if t["kategorie"] == "rechnung"]
    assert [t["titel"] for t in rechnungstreffer] == [nummer]
    assert "Beta Handel KG" in rechnungstreffer[0]["subtitel"]


@pytest.mark.asyncio
async def test_suche_zeigt_keine_rechnungen_ohne_abrechnungsrecht(
    client, make_mandant, make_user, make_kunde
):
    """Der /api/search-Router hat nur require_roles und KEIN require_recht --
    ohne das eigene Gate im Rechnungsblock wuerde jeder Mitarbeiter
    Rechnungsnummern, Kundennamen und Status sehen."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Gamma Werke")
    admin_token = await login(client, admin.email, "pw-123456")

    erstellt = await client.post(
        "/api/rechnungen",
        headers=auth_headers(admin_token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "300"},
    )
    nummer = erstellt.json()["rechnungsnummer"]

    ohne_recht = await _make_custom_account_typ_ohne_abrechnung(mandant)
    mitarbeiter = await _make_custom_user(mandant, ohne_recht)
    token = await login(client, mitarbeiter.email, mitarbeiter._plaintext_password)

    resp = await client.get(f"/api/search?q={nummer}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert [t for t in resp.json()["treffer"] if t["kategorie"] == "rechnung"] == []

    # Gegenprobe: derselbe Account kommt auch an die Liste nicht heran.
    assert (await client.get("/api/rechnungen", headers=auth_headers(token))).status_code == 403
