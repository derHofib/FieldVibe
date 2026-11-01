"""Nummernkreise ueber beleg_zaehler (Migration 0103): endgueltig geloeschte
Datensaetze duerfen keine Nummer wieder freigeben, parallele Vergabe bleibt
eindeutig, manuell vergebene Nummern oberhalb des Zaehlerstands kollidieren
nicht."""
import asyncio
import importlib.util
import os
import uuid

import pytest
from sqlalchemy import text

from app.db.session import system_session, tenant_session
from app.models.angebot import Angebot
from app.models.bestellung import Bestellung
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang
from app.services import numbering_service, papierkorb_service
from app.services.numbering_service import (
    next_angebotsnummer,
    next_bestellnummer,
    next_kundennummer,
    next_vorgangsnummer,
)
from tests.conftest import auth_headers, login

_TYPEN = ("kunde", "vorgang", "angebot", "bestellung")
_NEXT = {
    "kunde": next_kundennummer,
    "vorgang": next_vorgangsnummer,
    "angebot": next_angebotsnummer,
    "bestellung": next_bestellnummer,
}
_PRAEFIX = {"kunde": "K", "vorgang": "V", "angebot": "A", "bestellung": "B"}


async def _anlegen(typ: str, mandant, user, kunde_id: uuid.UUID, nummer: str | None = None):
    """Legt einen Datensatz mit automatischer (oder explizit gesetzter) Nummer
    in einer eigenen, committeten Mandanten-Transaktion an."""
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        if nummer is None:
            nummer = await _NEXT[typ](session, mandant.id)
        if typ == "kunde":
            obj = Kunde(
                mandant_id=mandant.id, kundennummer=nummer, name="Nummernkunde", portal_slug=uuid.uuid4().hex
            )
        elif typ == "vorgang":
            obj = Vorgang(
                mandant_id=mandant.id,
                vorgangsnummer=nummer,
                kunde_id=kunde_id,
                titel="Nummernvorgang",
                abrechnungsart="aufwand",
                leistungstyp="stoerung",
            )
        elif typ == "angebot":
            obj = Angebot(mandant_id=mandant.id, kunde_id=kunde_id, angebotsnummer=nummer, erstellt_von=user.id)
        else:
            obj = Bestellung(mandant_id=mandant.id, bestellnummer=nummer, erstellt_von=user.id)
        session.add(obj)
        await session.flush()
        return obj.id, nummer


async def _endgueltig_loeschen(typ: str, mandant, user, entity_id: uuid.UUID) -> None:
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        assert await papierkorb_service.soft_delete(
            session, entity_typ=typ, entity_id=entity_id, actor_user_id=user.id
        )
        assert await papierkorb_service.purge(session, entity_typ=typ, entity_id=entity_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("typ", _TYPEN)
async def test_nummer_nach_purge_nicht_wiederverwendet(typ, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)

    ids = [(await _anlegen(typ, mandant, user, kunde.id)) for _ in range(3)]
    assert [n for _, n in ids] == [f"{_PRAEFIX[typ]}-0000{i}" for i in (1, 2, 3)]

    # Mit COUNT(*)+1 waere die naechste Nummer jetzt "-00003" und damit
    # doppelt vergeben.
    await _endgueltig_loeschen(typ, mandant, user, ids[0][0])

    _, neue_nummer = await _anlegen(typ, mandant, user, kunde.id)
    assert neue_nummer == f"{_PRAEFIX[typ]}-00004"


@pytest.mark.asyncio
@pytest.mark.parametrize("typ", _TYPEN)
async def test_parallele_vergabe_liefert_eindeutige_nummern(typ, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)

    ergebnisse = await asyncio.gather(*[_anlegen(typ, mandant, user, kunde.id) for _ in range(8)])
    nummern = [n for _, n in ergebnisse]
    assert len(set(nummern)) == 8
    assert sorted(nummern) == [f"{_PRAEFIX[typ]}-{i:05d}" for i in range(1, 9)]


@pytest.mark.asyncio
async def test_parallele_anlage_ueber_api(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    kunden_resp = await asyncio.gather(
        *[client.post("/api/kunden", headers=auth_headers(token), json={"name": f"Kunde {i}"}) for i in range(6)]
    )
    assert [r.status_code for r in kunden_resp] == [201] * 6
    assert len({r.json()["kundennummer"] for r in kunden_resp}) == 6

    vorgang_resp = await asyncio.gather(
        *[
            client.post(
                "/api/vorgaenge",
                headers=auth_headers(token),
                json={
                    "kunde_id": str(kunde.id),
                    "titel": f"Vorgang {i}",
                    "abrechnungsart": "aufwand",
                    "leistungstyp": "stoerung",
                },
            )
            for i in range(6)
        ]
    )
    assert [r.status_code for r in vorgang_resp] == [201] * 6
    assert len({r.json()["vorgangsnummer"] for r in vorgang_resp}) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("typ", _TYPEN)
async def test_manuell_vergebene_nummer_ueber_zaehlerstand_kollidiert_nicht(
    typ, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    p = _PRAEFIX[typ]

    await _anlegen(typ, mandant, user, kunde.id, nummer=f"{p}-00002")
    geloescht_id, _ = await _anlegen(typ, mandant, user, kunde.id, nummer=f"{p}-00003")
    # Soft-geloeschte Datensaetze halten ihre Nummer weiter belegt.
    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        await papierkorb_service.soft_delete(
            session, entity_typ=typ, entity_id=geloescht_id, actor_user_id=user.id
        )

    nummern = [(await _anlegen(typ, mandant, user, kunde.id))[1] for _ in range(2)]
    assert nummern == [f"{p}-00001", f"{p}-00004"]


@pytest.mark.asyncio
async def test_manuelle_kundennummer_per_api_hoch(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    manuell = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Manuell", "kundennummer": "K-00050"}
    )
    assert manuell.status_code == 201
    for erwartet in ("K-00001", "K-00002"):
        resp = await client.post("/api/kunden", headers=auth_headers(token), json={"name": "Auto"})
        assert resp.status_code == 201
        assert resp.json()["kundennummer"] == erwartet


@pytest.mark.asyncio
async def test_nummernsuche_bricht_nach_max_versuchen_ab(monkeypatch, make_mandant, make_kunde):
    mandant = await make_mandant()
    for i in (1, 2, 3):
        await make_kunde(mandant=mandant, kundennummer=f"K-{i:05d}")
    monkeypatch.setattr(numbering_service, "_MAX_VERSUCHE", 3)

    async with tenant_session(mandant_id=mandant.id, is_super_admin=False) as session:
        with pytest.raises(RuntimeError, match="Keine freie Nummer"):
            await next_kundennummer(session, mandant.id)


@pytest.mark.asyncio
async def test_nummernkreise_sind_pro_mandant_getrennt(make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    user_a = await make_user(mandant=mandant_a, role="mandant_admin")
    kunde_a = await make_kunde(mandant=mandant_a)

    assert (await _anlegen("kunde", mandant_a, user_a, kunde_a.id))[1] == "K-00001"
    assert (await _anlegen("kunde", mandant_a, user_a, kunde_a.id))[1] == "K-00002"
    user_b = await make_user(mandant=mandant_b, role="mandant_admin")
    assert (await _anlegen("kunde", mandant_b, user_b, kunde_a.id))[1] == "K-00001"


def _migration_0103():
    pfad = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic", "versions", "0103_nummernkreise.py")
    spec = importlib.util.spec_from_file_location("migration_0103", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.asyncio
async def test_migration_initialisiert_zaehler_auf_max_plus_eins(make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    await make_mandant(name="Mandant ohne Daten")
    user = await make_user(mandant=mandant_a, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant_a, kundennummer="K-00001")

    # Mandant A: Hoechste Nummer ist ein soft-geloeschter Datensatz; Nummern
    # ausserhalb des Musters werden ignoriert. Mandant B hat nur Fremdformate.
    for nummer in ("K-00007", "K-00003", "K-ABC", "MANUELL-5", "K-12", "K-1234567890123"):
        await make_kunde(mandant=mandant_a, kundennummer=nummer)
    await make_kunde(mandant=mandant_b, kundennummer="X-9")
    await make_kunde(mandant=mandant_b, kundennummer="K-77x")
    async with system_session() as session:
        await session.execute(
            text("UPDATE kunden SET geloescht_am = now() WHERE mandant_id = :m AND kundennummer = 'K-00007'"),
            {"m": str(mandant_a.id)},
        )
        session.add(Vorgang(mandant_id=mandant_a.id, vorgangsnummer="V-00020", kunde_id=kunde.id, titel="x",
                            abrechnungsart="aufwand", leistungstyp="stoerung"))
        session.add(Angebot(mandant_id=mandant_a.id, kunde_id=kunde.id, angebotsnummer="A-00005", erstellt_von=user.id))
        session.add(Bestellung(mandant_id=mandant_a.id, bestellnummer="B-00002", erstellt_von=user.id))

        # Bestehender Rechnungszaehler darf unveraendert bleiben; die
        # Zaehler der neuen Belegarten werden zurueckgesetzt, als waere die
        # Migration noch nicht gelaufen.
        await session.execute(text("DELETE FROM beleg_zaehler"))
        await session.execute(
            text("INSERT INTO beleg_zaehler (mandant_id, belegart, naechste_nummer) VALUES (:m, 'rechnung', 42)"),
            {"m": str(mandant_a.id)},
        )

    modul = _migration_0103()
    async with system_session() as session:
        await session.run_sync(lambda s: modul.initialisiere_zaehler(s.connection()))
        # Zweiter Lauf aendert nichts (ON CONFLICT DO NOTHING).
        await session.run_sync(lambda s: modul.initialisiere_zaehler(s.connection()))
        zeilen = (await session.execute(text("SELECT mandant_id, belegart, naechste_nummer FROM beleg_zaehler"))).all()

    zaehler = {(str(z.mandant_id), z.belegart): z.naechste_nummer for z in zeilen}
    assert zaehler == {
        (str(mandant_a.id), "kunde"): 13,
        (str(mandant_a.id), "vorgang"): 21,
        (str(mandant_a.id), "angebot"): 6,
        (str(mandant_a.id), "bestellung"): 3,
        (str(mandant_a.id), "rechnung"): 42,
    }

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        assert await next_kundennummer(session, mandant_a.id) == "K-00013"
        assert await next_vorgangsnummer(session, mandant_a.id) == "V-00021"
    # Mandant B hatte kein passendes Format: Start bei 1.
    async with tenant_session(mandant_id=mandant_b.id, is_super_admin=False) as session:
        assert await next_kundennummer(session, mandant_b.id) == "K-00001"
