import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text

from app.api.routes import search as search_modul
from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.angebot import Angebot, AngebotPosition
from app.models.auftrag import Auftrag
from app.models.projekt import Projekt
from app.models.rechnung import Rechnung
from app.models.standort import Standort
from app.models.telefonat import Telefonat
from app.models.user import User
from app.services.organigramm_sync_service import besetzung_pflegen
from tests.conftest import auth_headers, login, trigger_aus


@pytest.mark.asyncio
async def test_search_finds_kunde_by_partial_name(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    await make_kunde(mandant=mandant, name="Café Sonnenschein")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "Sonnensch"})
    assert resp.status_code == 200
    kategorien = {t["kategorie"] for t in resp.json()["treffer"]}
    assert "kunde" in kategorien


@pytest.mark.asyncio
async def test_search_finds_vorgang_by_vorgangsnummer(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, vorgangsnummer="V-99999", titel="Ganz spezieller Titel"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "V-99999"})
    treffer = resp.json()["treffer"]
    assert any(t["id"] == str(vorgang.id) for t in treffer)


@pytest.mark.asyncio
async def test_search_finds_vorgang_by_kommentar_volltext(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Allgemeiner Titel")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Kaputte Zählerschranktür ausgetauscht"},
    )

    resp = await client.get(
        "/api/search", headers=auth_headers(token), params={"q": "Zählerschranktür"}
    )
    treffer = resp.json()["treffer"]
    assert any(t["id"] == str(vorgang.id) for t in treffer)


@pytest.mark.asyncio
async def test_search_with_hash_only_searches_tags(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.post("/api/tags", headers=auth_headers(token), json={"label": "wallbox"})

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "#wall"})
    treffer = resp.json()["treffer"]
    assert all(t["kategorie"] == "tag" for t in treffer)
    assert any(t["titel"] == "#wallbox" for t in treffer)


@pytest.mark.asyncio
async def test_search_is_scoped_to_own_mandant(client, make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    await make_kunde(mandant=mandant_b, name="Nur in Mandant B GmbH")
    token = await login(client, admin_a.email, "pw-123456")

    resp = await client.get(
        "/api/search", headers=auth_headers(token), params={"q": "Mandant B"}
    )
    assert resp.json()["treffer"] == []


# --- Erweiterte Suche: neue Kategorien, Filter, Rechte -----------------------


async def _admin(client, make_mandant, make_user, name="Testbetrieb"):
    mandant = await make_mandant(name=name)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    return mandant, admin, await login(client, admin.email, "pw-123456")


async def _suche(client, token, **params):
    resp = await client.get("/api/search", headers=auth_headers(token), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(daten, kategorie):
    return {t["id"] for t in daten["treffer"] if t["kategorie"] == kategorie}


async def _angebot(mandant, kunde, user, nummer, status="entwurf", preis="100.00", gueltig_bis=None):
    async with system_session(grund="test") as session:
        angebot = Angebot(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            angebotsnummer=nummer,
            status=status,
            erstellt_von=user.id,
            gueltig_bis=gueltig_bis,
        )
        session.add(angebot)
        await session.flush()
        session.add(
            AngebotPosition(
                mandant_id=mandant.id,
                angebot_id=angebot.id,
                position=1,
                beschreibung="Leistung",
                menge=Decimal("1"),
                einzelpreis=Decimal(preis),
            )
        )
        await session.flush()
        return angebot


async def _auftrag(mandant, user, titel, kunde=None, status="offen"):
    async with system_session(grund="test") as session:
        auftrag = Auftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id if kunde else None,
            titel=titel,
            status=status,
            erstellt_von=user.id,
        )
        session.add(auftrag)
        await session.flush()
        return auftrag


async def _projekt(mandant, user, name, archiviert=False):
    async with system_session(grund="test") as session:
        projekt = Projekt(mandant_id=mandant.id, name=name, archiviert=archiviert, erstellt_von=user.id)
        session.add(projekt)
        await session.flush()
        return projekt


async def _telefonat(mandant, user, kunde, partner_name, notiz=None, nummer=None):
    async with system_session(grund="test") as session:
        telefonat = Telefonat(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            partner_name=partner_name,
            partner_nummer=nummer,
            richtung="eingehend",
            ergebnis="erreicht",
            beginn=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
            notiz=notiz,
            erfasst_von=user.id,
        )
        session.add(telefonat)
        await session.flush()
        return telefonat


@pytest.mark.asyncio
async def test_search_neue_kategorien_und_felder(client, make_mandant, make_user, make_kunde):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Zeta Metallbau")
    angebot = await _angebot(mandant, kunde, admin, "A-ZZ-1", preis="100.00", gueltig_bis=date(2030, 1, 31))
    auftrag = await _auftrag(mandant, admin, "Zeta Hallendach", kunde=kunde)
    projekt = await _projekt(mandant, admin, "Zeta Neubau")
    telefonat = await _telefonat(mandant, admin, kunde, "Frau Zeta", notiz="x" * 200, nummer="0151-99")

    daten = await _suche(client, token, q="Zeta")
    assert angebot.id and str(angebot.id) in _ids(daten, "angebot")  # Kundenname trifft
    assert str(auftrag.id) in _ids(daten, "auftrag")
    assert str(projekt.id) in _ids(daten, "projekt")
    assert str(telefonat.id) in _ids(daten, "telefonat")

    treffer = {t["id"]: t for t in daten["treffer"]}
    a = treffer[str(angebot.id)]
    assert a["nummer"] == "A-ZZ-1" and a["status"] == "entwurf"
    assert a["kunde_name"] == "Zeta Metallbau"
    assert Decimal(a["betrag"]) == Decimal("119.00")
    assert a["datum"] == "2030-01-31"
    t = treffer[str(telefonat.id)]
    assert t["kunde_name"] == "Zeta Metallbau" and t["datum"] == "2026-03-04"
    assert len(t["zusatz"]) == 80
    assert treffer[str(auftrag.id)]["kunde_name"] == "Zeta Metallbau"

    # Angebotsnummer und Telefonnummer als Suchbegriff
    assert str(angebot.id) in _ids(await _suche(client, token, q="A-ZZ-1"), "angebot")
    assert str(telefonat.id) in _ids(await _suche(client, token, q="0151-99"), "telefonat")
    assert str(telefonat.id) in _ids(await _suche(client, token, q="xxxxx"), "telefonat")


@pytest.mark.asyncio
async def test_search_kunde_ueber_standort_ort_und_rechnung_ueber_kundenname(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Omega GmbH")
    async with system_session(grund="test") as session:
        session.add(
            Standort(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                bezeichnung="Filiale Nord",
                adresse={"ort": "Schleswigholstein"},
            )
        )
        session.add(
            Standort(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                bezeichnung="Filiale Süd",
                adresse={"ort": "Schleswigholstein"},
            )
        )
    daten = await _suche(client, token, q="Schleswig")
    # Zwei Standort-Treffer, ein Kunde -> dedupliziert
    assert [t["id"] for t in daten["treffer"] if t["kategorie"] == "kunde"] == [str(kunde.id)]
    assert daten["anzahl"]["kunde"] == 1

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "100", "faellig_am": "2030-05-05"},
    )
    rechnung = resp.json()
    daten = await _suche(client, token, q="Omega")
    r = next(t for t in daten["treffer"] if t["kategorie"] == "rechnung")
    assert r["id"] == rechnung["id"]
    assert Decimal(r["betrag"]) == Decimal("119.00")
    assert r["datum"] == "2030-05-05" and r["status"] == "entwurf" and r["nummer"] == rechnung["rechnungsnummer"]
    assert r["subtitel"] == f"Omega GmbH · entwurf"


@pytest.mark.asyncio
async def test_search_kategorie_parameter(client, make_mandant, make_user, make_kunde):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Kappa Bau")
    await _projekt(mandant, admin, "Kappa Projekt")
    daten = await _suche(client, token, q="Kappa", kategorie="projekt")
    assert {t["kategorie"] for t in daten["treffer"]} == {"projekt"}
    assert set(daten["anzahl"]) == {"projekt"}
    assert kunde.id


@pytest.mark.asyncio
async def test_search_nur_offen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Lambda AG")
    offen = await make_vorgang(mandant=mandant, kunde=kunde, titel="Lambda offen", status="in_arbeit")
    zu = await make_vorgang(mandant=mandant, kunde=kunde, titel="Lambda zu", status="abgeschlossen")
    ab = await make_vorgang(mandant=mandant, kunde=kunde, titel="Lambda abgerechnet", status="abgerechnet")
    ang_offen = await _angebot(mandant, kunde, admin, "A-L-1", status="versendet", gueltig_bis=date(2099, 1, 1))
    ang_abgelaufen = await _angebot(mandant, kunde, admin, "A-L-2", status="versendet", gueltig_bis=date(2000, 1, 1))
    ang_angenommen = await _angebot(mandant, kunde, admin, "A-L-3", status="angenommen")
    auftrag_offen = await _auftrag(mandant, admin, "Lambda Auftrag offen", status="in_arbeit")
    auftrag_zu = await _auftrag(mandant, admin, "Lambda Auftrag zu", status="abgeschlossen")
    projekt_offen = await _projekt(mandant, admin, "Lambda Projekt")
    projekt_arch = await _projekt(mandant, admin, "Lambda Archiv", archiviert=True)
    erst = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "10"}
    )
    rechnung_id = erst.json()["id"]

    voll = await _suche(client, token, q="Lambda")
    assert {str(zu.id), str(ab.id)} <= _ids(voll, "vorgang")

    daten = await _suche(client, token, q="Lambda", nur_offen=True)
    assert _ids(daten, "vorgang") == {str(offen.id)}
    assert _ids(daten, "angebot") == {str(ang_offen.id)}
    assert str(ang_abgelaufen.id) not in _ids(daten, "angebot") and str(ang_angenommen.id) not in _ids(daten, "angebot")
    assert _ids(daten, "auftrag") == {str(auftrag_offen.id)}
    assert _ids(daten, "projekt") == {str(projekt_offen.id)}
    assert rechnung_id in _ids(daten, "rechnung")  # Entwurf gilt als offen
    assert daten["anzahl"]["vorgang"] == 1 and daten["anzahl"]["projekt"] == 1
    assert str(auftrag_zu.id) not in _ids(daten, "auftrag") and str(projekt_arch.id) not in _ids(daten, "projekt")

    # Bezahlte Rechnung faellt raus
    bezahlt = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "10"}
    )
    bez_id = bezahlt.json()["id"]
    async with system_session(grund="test") as session:
        r = await session.get(Rechnung, UUID(bez_id))
        r.status = "bezahlt"
    daten = await _suche(client, token, q="Lambda", kategorie="rechnung", nur_offen=True)
    assert bez_id not in _ids(daten, "rechnung") and rechnung_id in _ids(daten, "rechnung")


@pytest.mark.asyncio
async def test_search_mir_zugewiesen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kollege = await make_user(mandant=mandant, role="mandant_admin", name="Kollege Kurz")
    kunde = await make_kunde(mandant=mandant, name="Sigma Werke")
    meins = await make_vorgang(mandant=mandant, kunde=kunde, titel="Sigma meins", zugewiesener_user_id=admin.id)
    fremd = await make_vorgang(mandant=mandant, kunde=kunde, titel="Sigma fremd", zugewiesener_user_id=kollege.id)
    await _auftrag(mandant, admin, "Sigma Auftrag")

    daten = await _suche(client, token, q="Sigma", mir_zugewiesen=True)
    assert {t["kategorie"] for t in daten["treffer"]} == {"vorgang"}
    assert set(daten["anzahl"]) == {"vorgang"}
    assert _ids(daten, "vorgang") == {str(meins.id)}

    ohne = await _suche(client, token, q="Sigma")
    treffer = {t["id"]: t for t in ohne["treffer"]}
    assert treffer[str(fremd.id)]["zusatz"] == "Kollege Kurz"
    assert treffer[str(fremd.id)]["kunde_name"] == "Sigma Werke"


@pytest.mark.asyncio
async def test_search_seit_filter(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Rho Technik")
    alt = await _projekt(mandant, admin, "Rho alt")
    neu = await _projekt(mandant, admin, "Rho neu")
    # Der updated_at-Trigger wuerde den Wert beim UPDATE sofort wieder ueberschreiben.
    async with trigger_aus("projekte", "trg_projekte_updated_at"):
        async with system_session(grund="test") as session:
            await session.execute(
                text("UPDATE projekte SET updated_at = '2020-01-01' WHERE id = :id"), {"id": alt.id}
            )
    daten = await _suche(client, token, q="Rho", seit="2024-01-01", kategorie="projekt")
    assert _ids(daten, "projekt") == {str(neu.id)}
    assert daten["anzahl"]["projekt"] == 1
    # Kunden haben kein sinnvolles Aenderungsdatum fuer den Filter -> ignoriert
    daten = await _suche(client, token, q="Rho", seit="2999-01-01", kategorie="kunde")
    assert _ids(daten, "kunde") == {str(kunde.id)}


@pytest.mark.asyncio
async def test_search_limit_offset_und_anzahl_deckel(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    for i in range(5):
        await make_kunde(mandant=mandant, name=f"Pagination Kunde {i}")

    seite1 = await _suche(client, token, q="Pagination", kategorie="kunde", limit=2)
    seite2 = await _suche(client, token, q="Pagination", kategorie="kunde", limit=2, offset=2)
    seite3 = await _suche(client, token, q="Pagination", kategorie="kunde", limit=2, offset=4)
    ids = [t["id"] for s in (seite1, seite2, seite3) for t in s["treffer"]]
    assert [len(s["treffer"]) for s in (seite1, seite2, seite3)] == [2, 2, 1]
    assert len(set(ids)) == 5
    assert seite1["anzahl"]["kunde"] == 5

    monkeypatch.setattr(search_modul, "ANZAHL_DECKEL", 3)
    gedeckelt = await _suche(client, token, q="Pagination", kategorie="kunde", limit=1)
    assert gedeckelt["anzahl"]["kunde"] == 3

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "x", "limit": 51})
    assert resp.status_code == 422
    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "x", "offset": -1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_exakter_nummerntreffer_zuerst(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Tau")
    await make_vorgang(mandant=mandant, kunde=kunde, vorgangsnummer="V-5000", titel="Anderer")
    exakt = await make_vorgang(mandant=mandant, kunde=kunde, vorgangsnummer="V-50", titel="Exakter")
    daten = await _suche(client, token, q="V-50", kategorie="vorgang")
    assert daten["treffer"][0]["id"] == str(exakt.id)


@pytest.mark.asyncio
async def test_search_ohne_abrechnungsrecht_keine_rechnung_und_angebot(
    client, make_mandant, make_user, make_kunde
):
    mandant, admin, admin_token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Ypsilon GmbH")
    await _angebot(mandant, kunde, admin, "A-Y-1")
    await client.post(
        "/api/rechnungen", headers=auth_headers(admin_token), json={"kunde_id": str(kunde.id), "betrag_netto": "5"}
    )
    mit = await _suche(client, admin_token, q="Ypsilon")
    assert {"rechnung", "angebot"} <= set(mit["anzahl"])

    async with system_session(grund="test") as session:
        typ = AccountTyp(mandant_id=mandant.id, name=f"Ohne-{uuid.uuid4().hex[:6]}")
        session.add(typ)
        await session.flush()
        session.add(AccountTypRecht(account_typ_id=typ.id, bereich="kunden", aktion="sehen", erlaubt=True))
        user = User(
            mandant_id=mandant.id,
            email=f"{uuid.uuid4().hex[:10]}@example.de",
            password_hash=hash_password("pw-123456"),
            role="custom",
            account_typ_id=typ.id,
            name="Ohne Rechte",
        )
        session.add(user)
        await session.flush()
        await besetzung_pflegen(session, user, neu=True)
    token = await login(client, user.email, "pw-123456")

    daten = await _suche(client, token, q="Ypsilon")
    kategorien = {t["kategorie"] for t in daten["treffer"]}
    assert not kategorien & {"rechnung", "angebot", "auftrag", "projekt"}
    assert not set(daten["anzahl"]) & {"rechnung", "angebot", "auftrag", "projekt"}
    assert "kunde" in daten["anzahl"]


@pytest.mark.asyncio
async def test_search_neue_kategorien_mandantengetrennt(client, make_mandant, make_user, make_kunde):
    mandant_a, admin_a, token_a = await _admin(client, make_mandant, make_user, name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    kunde_b = await make_kunde(mandant=mandant_b, name="Fremdkunde")
    await _angebot(mandant_b, kunde_b, admin_b, "A-GEHEIM-1")
    await _auftrag(mandant_b, admin_b, "Geheim Auftrag")
    await _projekt(mandant_b, admin_b, "Geheim Projekt")
    await _telefonat(mandant_b, admin_b, kunde_b, "Geheim Partner", notiz="Geheim Notiz")

    daten = await _suche(client, token_a, q="Geheim")
    assert daten["treffer"] == []
    assert all(n == 0 for n in daten["anzahl"].values())


@pytest.mark.asyncio
async def test_search_like_zeichen_sind_literal(client, make_mandant, make_user, make_kunde):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    await make_kunde(mandant=mandant, name="Normaler Kunde")
    prozent = await make_kunde(mandant=mandant, name="100% Dach")
    unterstrich = await make_kunde(mandant=mandant, name="Ab_cd")
    await make_kunde(mandant=mandant, name="Abxcd")

    assert _ids(await _suche(client, token, q="%", kategorie="kunde"), "kunde") == {str(prozent.id)}
    assert _ids(await _suche(client, token, q="_", kategorie="kunde"), "kunde") == {str(unterstrich.id)}
    assert _ids(await _suche(client, token, q="b_c", kategorie="kunde"), "kunde") == {str(unterstrich.id)}
    assert (await _suche(client, token, q="\\", kategorie="kunde"))["treffer"] == []


@pytest.mark.asyncio
async def test_search_hash_liefert_nur_tag_anzahl(client, make_mandant, make_user):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    await client.post("/api/tags", headers=auth_headers(token), json={"label": "wallbox"})
    daten = await _suche(client, token, q="#wall")
    assert daten["anzahl"] == {"tag": 1}


@pytest.mark.asyncio
async def test_search_nur_mit_q_bleibt_rueckwaertskompatibel(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, token = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Kompat GmbH", kundennummer="K-4711")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, vorgangsnummer="V-4711", titel="Kompat Titel")
    daten = await _suche(client, token, q="Kompat")
    treffer = {t["id"]: t for t in daten["treffer"]}
    assert treffer[str(kunde.id)]["subtitel"] == "K-4711"
    assert treffer[str(vorgang.id)]["subtitel"] == "neu"
    assert treffer[str(vorgang.id)]["titel"] == "V-4711: Kompat Titel"
