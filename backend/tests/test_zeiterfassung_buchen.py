"""Stufe 2 (docs/konzepte/ZEITERFASSUNG.md): Buchungsablauf vermerkt ->
vorgemerkt -> gebucht -> (abgerechnet), inkl. Sperrregeln, Protokoll und
Rechnungsvorschlaege nur aus gebuchter Zeit."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.user import User
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login

# Volles "vorgaenge"/"abrechnung"-Recht fuer alle in diesem Modul erstellten
# Account-Typen -- die eigentlich interessante Rechte-Variable in diesen
# Tests ist ausschliesslich darf_zeiten_buchen (Einzelrecht, siehe Konzept
# 5.4), nicht die normale Rechte-Matrix. Ohne diese Zeilen wuerde jede
# Route schon am router-weiten require_recht("vorgaenge", "sehen") mit 403
# scheitern, bevor die eigentliche Buchungslogik ueberhaupt greift.
_VOLLE_RECHTE = {
    "vorgaenge": {"sehen", "erstellen", "bearbeiten", "loeschen"},
    "abrechnung": {"sehen", "erstellen", "bearbeiten", "loeschen"},
}


async def _erstellen(mandant, name, *, darf_buchen):
    """Ein role='custom'-User mit einem eigenen Account-Typ -- zeigt u.a.,
    dass das Recht "Zeiten buchen" an keine Rolle gebunden ist (Konzept
    5.4), anders als ein 'mandant_admin', der es ohnehin immer hat."""
    async with system_session() as session:
        account_typ = AccountTyp(
            mandant_id=mandant.id, name=f"Typ-{name}-{darf_buchen}", darf_zeiten_buchen=darf_buchen
        )
        session.add(account_typ)
        await session.flush()
        for bereich, aktionen in _VOLLE_RECHTE.items():
            for aktion in ("sehen", "erstellen", "bearbeiten", "loeschen"):
                session.add(
                    AccountTypRecht(
                        account_typ_id=account_typ.id,
                        bereich=bereich,
                        aktion=aktion,
                        erlaubt=aktion in aktionen,
                    )
                )
        await session.flush()
        user = User(
            mandant_id=mandant.id,
            email=f"{name.lower().replace(' ', '.')}@example.de",
            password_hash=hash_password("pw-123456"),
            role="custom",
            account_typ_id=account_typ.id,
            name=name,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        user._plaintext_password = "pw-123456"
        return user


async def _fertigen_eintrag(mandant, vorgang, techniker, *, taetigkeit="Erledigt", stunden=1, start_offset_h=-3):
    async with system_session() as session:
        start = datetime.now(timezone.utc) + timedelta(hours=start_offset_h)
        eintrag = Zeiterfassung(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            techniker_id=techniker.id,
            start_at=start,
            ende_at=start + timedelta(hours=stunden),
            kategorie="auftrag",
            taetigkeit=taetigkeit,
            abrechenbar=True,
        )
        session.add(eintrag)
        await session.flush()
        await session.refresh(eintrag)
        return eintrag


@pytest.mark.asyncio
async def test_eigene_zeit_vormerken_und_zurueckziehen(
    client, make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Eins", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/vormerken", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 200
    assert resp.json()[0]["buchungsstatus"] == "vorgemerkt"

    zurueck = await client.post(
        "/api/zeiterfassung/vormerkung-zurueckziehen",
        headers=auth_headers(token),
        json={"ids": [str(eintrag.id)]},
    )
    assert zurueck.status_code == 200
    assert zurueck.json()[0]["buchungsstatus"] == "vermerkt"


@pytest.mark.asyncio
async def test_vormerken_ohne_taetigkeit_schlaegt_fehl(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Zwei", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker, taetigkeit=None)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/vormerken", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 400
    assert "Tätigkeit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_vormerken_laufender_timer_schlaegt_fehl(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Drei", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session() as session:
        eintrag = Zeiterfassung(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            techniker_id=techniker.id,
            start_at=datetime.now(timezone.utc) - timedelta(hours=1),
            kategorie="auftrag",
            taetigkeit="Laufend",
        )
        session.add(eintrag)
        await session.flush()
        await session.refresh(eintrag)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/vormerken", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 400
    assert "läuft" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_vormerken_fremde_zeit_ohne_recht_verboten(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker1 = await _erstellen(mandant, "Techniker Vier", darf_buchen=False)
    techniker2 = await _erstellen(mandant, "Techniker Fuenf", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker1)
    token2 = await login(client, techniker2.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/vormerken", headers=auth_headers(token2), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 400
    assert "nicht deine Zeit" in resp.json()["detail"]

    async with system_session() as session:
        unveraendert = await session.get(Zeiterfassung, eintrag.id)
        assert unveraendert.buchungsstatus == "vermerkt"


@pytest.mark.asyncio
async def test_buchungsberechtigter_bucht_fremden_eintrag_direkt(
    client, make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Sechs", darf_buchen=False)
    buchende = await _erstellen(mandant, "Buchende Berta", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker)
    token = await login(client, buchende.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 200
    body = resp.json()[0]
    assert body["buchungsstatus"] == "gebucht"
    assert body["gebucht_von"] == str(buchende.id)


@pytest.mark.asyncio
async def test_buchen_ohne_recht_verboten(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Sieben", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_mit_buchungsrecht_bucht_eigene_zeit_selbst_gesperrt(
    client, make_mandant, make_kunde, make_vorgang
):
    """'Techniker mit Buchungsrecht bucht selbst -> Eintrag gesperrt'
    (Konzept 10, Stufe-2-Playwright-Plan, hier als Backend-Aequivalent)."""
    mandant = await make_mandant()
    buchender_techniker = await _erstellen(mandant, "Technikerin Acht", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, buchender_techniker)
    token = await login(client, buchender_techniker.email, "pw-123456")

    buchen = await client.post(
        "/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(eintrag.id)]}
    )
    assert buchen.status_code == 200

    patch = await client.patch(
        f"/api/zeiterfassung/{eintrag.id}", headers=auth_headers(token), json={"taetigkeit": "geändert"}
    )
    assert patch.status_code == 409

    delete = await client.delete(f"/api/zeiterfassung/{eintrag.id}", headers=auth_headers(token))
    assert delete.status_code == 409


@pytest.mark.asyncio
async def test_buchung_stornieren_ohne_grund_schlaegt_fehl(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    buchende = await _erstellen(mandant, "Buchende Neun", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, buchende)
    token = await login(client, buchende.email, "pw-123456")
    await client.post("/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(eintrag.id)]})

    resp = await client.post(
        "/api/zeiterfassung/buchung-stornieren",
        headers=auth_headers(token),
        json={"ids": [str(eintrag.id)], "grund": "  "},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_buchung_stornieren_mit_grund_setzt_zurueck(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    buchende = await _erstellen(mandant, "Buchende Zehn", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, buchende)
    token = await login(client, buchende.email, "pw-123456")
    await client.post("/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(eintrag.id)]})

    resp = await client.post(
        "/api/zeiterfassung/buchung-stornieren",
        headers=auth_headers(token),
        json={"ids": [str(eintrag.id)], "grund": "Falscher Vorgang gebucht"},
    )
    assert resp.status_code == 200
    body = resp.json()[0]
    assert body["buchungsstatus"] == "vermerkt"
    assert body["gebucht_von"] is None

    verlauf = await client.get(f"/api/zeiterfassung/{eintrag.id}/verlauf", headers=auth_headers(token))
    aktionen = [e["aktion"] for e in verlauf.json()]
    assert "buchung_storniert" in aktionen
    storno = next(e for e in verlauf.json() if e["aktion"] == "buchung_storniert")
    assert storno["grund"] == "Falscher Vorgang gebucht"


@pytest.mark.asyncio
async def test_alles_oder_nichts_beim_vormerken(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Elf", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    gueltig = await _fertigen_eintrag(mandant, vorgang, techniker, taetigkeit="Gültig")
    ungueltig = await _fertigen_eintrag(mandant, vorgang, techniker, taetigkeit=None)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/zeiterfassung/vormerken",
        headers=auth_headers(token),
        json={"ids": [str(gueltig.id), str(ungueltig.id)]},
    )
    assert resp.status_code == 400

    async with system_session() as session:
        db_gueltig = await session.get(Zeiterfassung, gueltig.id)
        assert db_gueltig.buchungsstatus == "vermerkt"


@pytest.mark.asyncio
async def test_fremden_eintrag_bearbeiten_grund_pflicht(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Zwoelf", darf_buchen=False)
    buchende = await _erstellen(mandant, "Buchende Dreizehn", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker)
    token = await login(client, buchende.email, "pw-123456")

    ohne_grund = await client.patch(
        f"/api/zeiterfassung/{eintrag.id}", headers=auth_headers(token), json={"taetigkeit": "Korrigiert"}
    )
    assert ohne_grund.status_code == 400

    mit_grund = await client.patch(
        f"/api/zeiterfassung/{eintrag.id}",
        headers=auth_headers(token),
        json={"taetigkeit": "Korrigiert", "grund": "Techniker vergaß Tätigkeit"},
    )
    assert mit_grund.status_code == 200
    assert mit_grund.json()["taetigkeit"] == "Korrigiert"

    verlauf = await client.get(f"/api/zeiterfassung/{eintrag.id}/verlauf", headers=auth_headers(token))
    geaendert = next(e for e in verlauf.json() if e["aktion"] == "geaendert")
    assert geaendert["grund"] == "Techniker vergaß Tätigkeit"


@pytest.mark.asyncio
async def test_fremden_eintrag_bearbeiten_ohne_recht_404(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker1 = await _erstellen(mandant, "Techniker Vierzehn", darf_buchen=False)
    techniker2 = await _erstellen(mandant, "Techniker Fuenfzehn", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    eintrag = await _fertigen_eintrag(mandant, vorgang, techniker1)
    token2 = await login(client, techniker2.email, "pw-123456")

    resp = await client.patch(
        f"/api/zeiterfassung/{eintrag.id}", headers=auth_headers(token2), json={"taetigkeit": "x"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fremden_laufenden_timer_beenden_erfordert_grund(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Sechzehn", darf_buchen=False)
    buchende = await _erstellen(mandant, "Buchende Siebzehn", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session() as session:
        laufend = Zeiterfassung(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            techniker_id=techniker.id,
            start_at=datetime.now(timezone.utc) - timedelta(hours=2),
            kategorie="auftrag",
        )
        session.add(laufend)
        await session.flush()
        await session.refresh(laufend)
    token = await login(client, buchende.email, "pw-123456")

    ohne_grund = await client.post(f"/api/zeiterfassung/{laufend.id}/stop", headers=auth_headers(token))
    assert ohne_grund.status_code == 400

    ende = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    mit_grund = await client.post(
        f"/api/zeiterfassung/{laufend.id}/stop",
        headers=auth_headers(token),
        json={"ende_at": ende, "grund": "Techniker im Feierabend vergessen zu stoppen"},
    )
    assert mit_grund.status_code == 200
    assert mit_grund.json()["ende_at"] is not None


@pytest.mark.asyncio
async def test_fremden_timer_beenden_ohne_recht_404(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker1 = await _erstellen(mandant, "Techniker Achtzehn", darf_buchen=False)
    techniker2 = await _erstellen(mandant, "Techniker Neunzehn", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    async with system_session() as session:
        laufend = Zeiterfassung(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            techniker_id=techniker1.id,
            start_at=datetime.now(timezone.utc) - timedelta(hours=1),
            kategorie="auftrag",
        )
        session.add(laufend)
        await session.flush()
        await session.refresh(laufend)
    token2 = await login(client, techniker2.email, "pw-123456")

    resp = await client.post(f"/api/zeiterfassung/{laufend.id}/stop", headers=auth_headers(token2))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fuer_anderen_nachtragen_erfordert_recht(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker1 = await _erstellen(mandant, "Techniker Zwanzig", darf_buchen=False)
    techniker2 = await _erstellen(mandant, "Techniker Einundzwanzig", darf_buchen=False)
    buchende = await _erstellen(mandant, "Buchende Zweiundzwanzig", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "start_at": start.isoformat(),
        "ende_at": (start + timedelta(minutes=30)).isoformat(),
        "kategorie": "auftrag",
        "vorgang_id": str(vorgang.id),
        "techniker_id": str(techniker2.id),
    }

    token1 = await login(client, techniker1.email, "pw-123456")
    verboten = await client.post("/api/zeiterfassung/manuell", headers=auth_headers(token1), json=payload)
    assert verboten.status_code == 403

    buchende_token = await login(client, buchende.email, "pw-123456")
    erlaubt = await client.post(
        "/api/zeiterfassung/manuell", headers=auth_headers(buchende_token), json=payload
    )
    assert erlaubt.status_code == 201
    assert erlaubt.json()["techniker_id"] == str(techniker2.id)
    assert erlaubt.json()["buchungsstatus"] == "vermerkt"


@pytest.mark.asyncio
async def test_rechnungsvorschlaege_nur_aus_gebuchter_zeit(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    buchende = await _erstellen(mandant, "Buchende Dreiundzwanzig", darf_buchen=True)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    vermerkt = await _fertigen_eintrag(mandant, vorgang, buchende, taetigkeit="Noch nicht gebucht", stunden=1)
    gebucht = await _fertigen_eintrag(mandant, vorgang, buchende, taetigkeit="Gebucht", stunden=2)
    token = await login(client, buchende.email, "pw-123456")
    await client.post("/api/zeiterfassung/buchen", headers=auth_headers(token), json={"ids": [str(gebucht.id)]})

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)}
    )
    rechnung_id = created.json()["id"]
    resp = await client.get(f"/api/rechnungen/{rechnung_id}/positionsvorschlaege", headers=auth_headers(token))
    assert resp.status_code == 200
    zeit_vorschlaege = [v for v in resp.json() if v["quelle"] == "zeit"]
    assert len(zeit_vorschlaege) == 1
    assert zeit_vorschlaege[0]["menge"] == "2.00"


@pytest.mark.asyncio
async def test_protokoll_angelegt_beim_anlegen(client, make_mandant, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await _erstellen(mandant, "Techniker Vierundzwanzig", darf_buchen=False)
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")
    start = datetime.now(timezone.utc) - timedelta(hours=1)

    created = await client.post(
        "/api/zeiterfassung/manuell",
        headers=auth_headers(token),
        json={
            "start_at": start.isoformat(),
            "ende_at": (start + timedelta(minutes=30)).isoformat(),
            "kategorie": "auftrag",
            "vorgang_id": str(vorgang.id),
            "taetigkeit": "Test",
        },
    )
    eintrag_id = created.json()["id"]

    verlauf = await client.get(f"/api/zeiterfassung/{eintrag_id}/verlauf", headers=auth_headers(token))
    assert verlauf.status_code == 200
    aktionen = [e["aktion"] for e in verlauf.json()]
    assert aktionen == ["angelegt"]
