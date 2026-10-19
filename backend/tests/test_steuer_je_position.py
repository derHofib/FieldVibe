"""Steuer je Rechnungsposition (Migration 0104, steuer_service).

Zentral: der Golden-Test gegen die alte Einzelsatz-Formel. Abweichungen sind
nur an exakten Halb-Cent-Faellen erlaubt (alt: ROUND_HALF_EVEN, neu:
kaufmaennisch ROUND_HALF_UP wie Postgres round()) und werden hier explizit
dokumentiert.
"""
import asyncio
import csv
import io
import os
import random
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import steuer_service
from app.services.auswertung_service import KontoNichtKonfiguriert, _erloeskonto
from tests.conftest import auth_headers, login

_CENT = Decimal("0.01")
_BACKEND = os.path.dirname(os.path.dirname(__file__))

_FIRMENDATEN_E_RECHNUNG = {
    "e_rechnung_aktiv": True,
    "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
    "ust_idnr": "DE123456789",
}


_KU_HINWEIS = "Steuerbefreit nach § 19 UStG (Kleinunternehmerregelung)"


def _d(wert) -> Decimal:
    return Decimal(str(wert))


def _position(menge, preis, satz, kategorie="S") -> RechnungPosition:
    return RechnungPosition(
        menge=_d(menge), einzelpreis=_d(preis), steuer_satz=_d(satz), steuer_kategorie=kategorie
    )


def _beleg(satz, netto="0") -> Rechnung:
    return Rechnung(betrag_netto=_d(netto), mwst_satz=_d(satz))


def _alt_netto(positionen: list[tuple]) -> Decimal:
    return sum((_d(m) * _d(p) for m, p in positionen), Decimal("0")).quantize(_CENT)


def _alt_brutto(netto: Decimal, satz) -> Decimal:
    return (netto + netto * _d(satz) / Decimal("100")).quantize(_CENT)


def _neu_brutto(netto: Decimal, satz) -> Decimal:
    """Erwartung an exakten Halb-Cent-Faellen: kaufmaennisch gerundete Steuer."""
    return netto + (netto * _d(satz) / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)


def _ist_halbcent(wert: Decimal) -> bool:
    return (wert * 1000) % 10 == 5 and (wert * 1000) == (wert * 1000).to_integral_value()


# --- Golden-Test gegen die alte Formel ------------------------------------

# Anzahl der Raster-Faelle (Netto 0,01..50,00 x Saetze 19/7/0, je ohne und mit
# Position geprueft), in denen alt und neu abweichen (von 15000) -- ausschliesslich Halb-Cent-Faelle.
_ERWARTETE_RASTER_ABWEICHUNGEN = 50


def test_golden_raster_alt_gegen_neu():
    abweichungen = []
    for cent in range(1, 5001):
        netto = Decimal(cent) / 100
        for satz in ("19", "7", "0"):
            alt = _alt_brutto(netto, satz)
            ohne_position = steuer_service.brutto_summe(steuer_service.steuer_gruppen(_beleg(satz, netto), []))
            kategorie = "E" if satz == "0" else "S"
            mit_position = steuer_service.brutto_summe(
                steuer_service.steuer_gruppen(_beleg(satz), [_position(1, netto, satz, kategorie)])
            )
            assert ohne_position == mit_position, (netto, satz)
            if ohne_position == alt:
                continue
            # Abweichung nur zulaessig, wenn die Steuer exakt auf einem Halb-Cent liegt ...
            assert _ist_halbcent(netto * _d(satz) / Decimal("100")), (netto, satz, alt, ohne_position)
            # ... und dann gilt der kaufmaennisch gerundete Wert.
            assert ohne_position == _neu_brutto(netto, satz), (netto, satz)
            abweichungen.append((netto, satz))
    assert len(abweichungen) == _ERWARTETE_RASTER_ABWEICHUNGEN


# (Positionen als (menge, preis), Satz) -- Einzelsatz-Belege ohne Halb-Cent-Fall:
# muss exakt der alten Formel entsprechen.
_BEISPIELE_IDENTISCH = [
    ([(2, "49.90"), (1, "120.00")], "19"),
    ([(3, "19.99"), (1.25, "80.00"), (7.5, "12.34")], "7"),
    ([(1, "1000.00")], "19"),
    ([(0.25, "13.33"), (4, "0.07"), (12, "8.88")], "19"),
    ([(10, "0.01")], "7"),
    ([(1, "99.99"), (1, "0.01")], "0"),
    ([(8.5, "42.00"), (2.75, "63.40"), (1, "15.95")], "19"),
]


@pytest.mark.parametrize("positionen,satz", _BEISPIELE_IDENTISCH)
def test_golden_beispielrechnungen_identisch(positionen, satz):
    netto_alt = _alt_netto(positionen)
    kategorie = "E" if satz == "0" else "S"
    gruppen = steuer_service.steuer_gruppen(
        _beleg(satz), [_position(m, p, satz, kategorie) for m, p in positionen]
    )
    assert len(gruppen) == 1
    assert steuer_service.netto_summe(gruppen) == netto_alt
    assert steuer_service.brutto_summe(gruppen) == _alt_brutto(netto_alt, satz)


def test_golden_halbcent_netto_der_positionssumme():
    # 0,5 x 33,33 = 16,665: alt (HALF_EVEN) 16,66, neu (HALF_UP) 16,67.
    positionen = [(0.5, "33.33")]
    gruppen = steuer_service.steuer_gruppen(_beleg("19"), [_position(0.5, "33.33", "19")])
    assert _alt_netto(positionen) == Decimal("16.66")
    assert steuer_service.netto_summe(gruppen) == Decimal("16.67")
    assert steuer_service.steuer_summe(gruppen) == Decimal("3.17")
    assert steuer_service.brutto_summe(gruppen) == Decimal("19.84")


def test_golden_halbcent_steuer():
    # 3,50 x 7 % = 0,245: alt (HALF_EVEN) 0,24, neu (HALF_UP) 0,25.
    gruppen = steuer_service.steuer_gruppen(_beleg("7"), [_position(1, "3.50", "7")])
    assert steuer_service.steuer_summe(gruppen) == Decimal("0.25")
    assert steuer_service.brutto_summe(gruppen) == Decimal("3.75")
    assert _alt_brutto(Decimal("3.50"), "7") == Decimal("3.74")


# --- Rechenkern ----------------------------------------------------------


def test_gruppen_sortierung_und_rundung_je_gruppe_nicht_je_position():
    # Drei Positionen zu 0,10 EUR @ 19 %: je Position 0,019 -> 0,02 (Summe 0,06),
    # je Gruppe 0,30 * 19 % = 0,057 -> 0,06. Die Gruppe rundet, nicht die Position.
    positionen = [_position(1, "0.10", "19")] * 3 + [_position(1, "50.00", "7"), _position(1, "20.00", "0", "E")]
    gruppen = steuer_service.steuer_gruppen(_beleg("19"), positionen)
    assert [(g.kategorie, g.satz) for g in gruppen] == [("S", _d("19.00")), ("S", _d("7.00")), ("E", _d("0.00"))]
    assert gruppen[0].netto == Decimal("0.30")
    assert gruppen[0].steuer == Decimal("0.06")
    assert gruppen[1].steuer == Decimal("3.50")
    assert steuer_service.netto_summe(gruppen) == Decimal("70.30")
    assert steuer_service.brutto_summe(gruppen) == Decimal("73.86")


def test_ohne_positionen_eine_gruppe_aus_beleg():
    regel = steuer_service.steuer_gruppen(_beleg("19", "100"), [])
    assert [(g.kategorie, g.satz, g.netto, g.steuer) for g in regel] == [("S", _d("19.00"), _d("100"), _d("19"))]
    befreit = steuer_service.steuer_gruppen(_beleg("0", "100"), [])
    assert [(g.kategorie, g.satz, g.steuer) for g in befreit] == [("E", _d("0.00"), _d("0"))]


def test_storno_negation_summiert_auf_null():
    positionen = [_position(1, "3.50", "7"), _position(1, "10.10", "19"), _position(0.5, "33.33", "19")]
    negiert = [_position(p.menge, -p.einzelpreis, p.steuer_satz) for p in positionen]
    summe = steuer_service.brutto_summe(steuer_service.steuer_gruppen(_beleg("19"), positionen))
    gegen = steuer_service.brutto_summe(steuer_service.steuer_gruppen(_beleg("19"), negiert))
    assert summe + gegen == 0


# --- SQL == Python -----------------------------------------------------------


async def _belege_anlegen(mandant, kunde, user, faelle: list[tuple[str, list[tuple], str | None]]) -> None:
    """faelle: (Beleg-Satz, Positionen als (menge, preis, satz, kategorie), betrag_netto ohne Positionen)."""
    async with system_session() as session:
        for i, (beleg_satz, positionen, netto_ohne) in enumerate(faelle):
            rechnung = Rechnung(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                rechnungsnummer=f"R-SQL-{i}",
                betrag_netto=_d(netto_ohne or "0"),
                mwst_satz=_d(beleg_satz),
                erstellt_von=user.id,
            )
            session.add(rechnung)
            await session.flush()
            for n, (menge, preis, satz, kategorie) in enumerate(positionen, start=1):
                session.add(
                    RechnungPosition(
                        mandant_id=mandant.id,
                        rechnung_id=rechnung.id,
                        position=n,
                        beschreibung=f"P{n}",
                        menge=_d(menge),
                        einzelpreis=_d(preis),
                        steuer_satz=_d(satz),
                        steuer_kategorie=kategorie,
                    )
                )
        await session.commit()


@pytest.mark.asyncio
async def test_sql_summen_gleich_python_summen(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    zufall = random.Random(20261019)
    faelle: list[tuple[str, list[tuple], str | None]] = []
    for _ in range(60):
        positionen = [
            (
                f"{zufall.randint(1, 2000) / 100:.2f}",
                f"{zufall.randint(1, 20000) / 100:.2f}",
                zufall.choice(["19", "7"]),
                "S",
            )
            for _ in range(zufall.randint(1, 5))
        ]
        faelle.append(("19", positionen, None))
    # Halb-Cent-Faelle, Mehrgruppen, Befreiung, negative Positionen (Storno) und Belege ohne Positionen.
    faelle += [
        ("19", [("1", "3.50", "7", "S")], None),
        ("19", [("0.5", "33.33", "19", "S")], None),
        ("19", [("1", "10.10", "19", "S"), ("1", "3.50", "7", "S")], None),
        ("19", [("1", "-10.10", "19", "S"), ("1", "-3.50", "7", "S"), ("0.5", "-33.33", "19", "S")], None),
        ("0", [("2", "49.90", "0", "E")], None),
        ("19", [], "1.50"),
        ("7", [], "3.50"),
        ("0", [], "100.00"),
        ("19", [], "-1.50"),
    ]
    await _belege_anlegen(mandant, kunde, user, faelle)

    async with system_session() as session:
        zeilen = (
            await session.execute(
                select(
                    Rechnung.id,
                    steuer_service.netto_sql(),
                    steuer_service.steuer_sql(),
                    steuer_service.brutto_sql(),
                )
            )
        ).all()
        assert len(zeilen) == len(faelle)
        for rechnung_id, netto_sql, steuer_sql, brutto_sql in zeilen:
            rechnung = await session.get(Rechnung, rechnung_id)
            positionen = (
                (
                    await session.execute(
                        select(RechnungPosition)
                        .where(RechnungPosition.rechnung_id == rechnung_id)
                        .order_by(RechnungPosition.position)
                    )
                )
                .scalars()
                .all()
            )
            gruppen = steuer_service.steuer_gruppen(rechnung, positionen)
            assert netto_sql == steuer_service.netto_summe(gruppen), rechnung.rechnungsnummer
            assert steuer_sql == steuer_service.steuer_summe(gruppen), rechnung.rechnungsnummer
            assert brutto_sql == steuer_service.brutto_summe(gruppen), rechnung.rechnungsnummer
            assert brutto_sql == netto_sql + steuer_sql


# --- DB-Constraints -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kategorie,satz",
    [("X", "0"), ("Z", "7"), ("E", "19"), ("AE", "0.01"), ("S", "100.01"), ("S", "-1")],
)
async def test_constraints_lehnen_unzulaessige_steuerfelder_ab(make_mandant, make_user, make_kunde, kategorie, satz):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    with pytest.raises(IntegrityError):
        async with system_session() as session:
            rechnung = Rechnung(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                rechnungsnummer="R-CK-1",
                betrag_netto=Decimal("0"),
                mwst_satz=Decimal("19"),
                erstellt_von=user.id,
            )
            session.add(rechnung)
            await session.flush()
            session.add(
                RechnungPosition(
                    mandant_id=mandant.id,
                    rechnung_id=rechnung.id,
                    position=1,
                    beschreibung="x",
                    einzelpreis=Decimal("1"),
                    steuer_kategorie=kategorie,
                    steuer_satz=_d(satz),
                )
            )
            await session.commit()


# --- Migration ------------------------------------------------------------------


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


def _sync_engine():
    return create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


def _spalten(engine, tabelle: str) -> dict:
    return {c["name"]: c for c in inspect(engine).get_columns(tabelle)}


def _checks(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_check_constraints("rechnung_positionen")}


_STEUER_CHECKS = {
    "ck_rechnung_positionen_steuer_kategorie_valid",
    "ck_rechnung_positionen_steuer_satz_zu_kategorie",
    "ck_rechnung_positionen_steuer_satz_bereich",
}


@pytest.mark.asyncio
async def test_migration_0104_up_down_up_mit_backfill(make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    engine = _sync_engine()
    belege = {"19.00": uuid.uuid4(), "7.00": uuid.uuid4(), "0.00": uuid.uuid4()}
    try:
        await _migrieren("downgrade", "0103")
        assert not {"steuer_kategorie", "steuer_satz"} & set(_spalten(engine, "rechnung_positionen"))
        assert not _STEUER_CHECKS & _checks(engine)

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for i, (satz, rechnung_id) in enumerate(belege.items()):
                conn.execute(
                    text(
                        "INSERT INTO rechnungen (id, mandant_id, kunde_id, rechnungsnummer, betrag_netto, "
                        "mwst_satz, erstellt_von) VALUES (:id, :m, :k, :nr, 0, :satz, :u)"
                    ),
                    {"id": rechnung_id, "m": mandant.id, "k": kunde.id, "nr": f"R-MIG-{i}", "satz": satz, "u": user.id},
                )
                for position in (1, 2):
                    conn.execute(
                        text(
                            "INSERT INTO rechnung_positionen (mandant_id, rechnung_id, position, beschreibung, "
                            "menge, einzelpreis) VALUES (:m, :r, :p, 'x', 1, 10)"
                        ),
                        {"m": mandant.id, "r": rechnung_id, "p": position},
                    )

        await _migrieren("upgrade", "head")

        spalten = _spalten(engine, "rechnung_positionen")
        assert spalten["steuer_kategorie"]["nullable"] is False
        assert spalten["steuer_satz"]["nullable"] is False
        assert _STEUER_CHECKS <= _checks(engine)
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for satz, rechnung_id in belege.items():
                zeilen = conn.execute(
                    text("SELECT steuer_kategorie, steuer_satz FROM rechnung_positionen WHERE rechnung_id = :r"),
                    {"r": rechnung_id},
                ).all()
                erwartet = ("E" if satz == "0.00" else "S", Decimal(satz))
                assert zeilen == [erwartet, erwartet], satz
            # RLS bleibt auf der Tabelle aktiv (keine neue Policy noetig).
            relrls, relforce = conn.execute(
                text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'rechnung_positionen'")
            ).one()
            assert relrls and relforce
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


# --- API: Mehrgruppen, Gating, Kleinunternehmer, Storno ------------------------------


async def _admin(client, make_mandant, make_user, make_kunde, firmendaten: dict | None = None, **kunde_kw):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, **kunde_kw)
    token = await login(client, admin.email, "pw-123456")
    if firmendaten is not None:
        resp = await client.patch(
            "/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": firmendaten}
        )
        assert resp.status_code == 200
    return token, kunde


_MISCHBELEG_POSITIONEN = [
    {"beschreibung": "Material 19", "menge": "1", "einzelpreis": "10.10"},
    {"beschreibung": "Material 7", "menge": "1", "einzelpreis": "3.50", "steuer_satz": "7"},
]


async def _mischbeleg(client, token, kunde, **extra) -> dict:
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            "positionen": _MISCHBELEG_POSITIONEN,
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_mischbeleg_gruppen_und_summen(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)

    assert rechnung["steuergruppen"] == [
        {"kategorie": "S", "satz": "19.00", "netto": "10.10", "steuer": "1.92", "hinweis": None, "hinweise": []},
        {"kategorie": "S", "satz": "7.00", "netto": "3.50", "steuer": "0.25", "hinweis": None, "hinweise": []},
    ]
    assert rechnung["betrag_netto"] == "13.60"
    assert rechnung["betrag_steuer"] == "2.17"
    assert rechnung["betrag_brutto"] == "15.77"
    assert [(p["steuer_kategorie"], p["steuer_satz"]) for p in rechnung["positionen"]] == [
        ("S", "19.00"),
        ("S", "7.00"),
    ]


@pytest.mark.asyncio
async def test_uebersicht_filter_und_summenzeile_stimmen_mit_detail(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    misch = await _mischbeleg(client, token, kunde)
    einfach = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "100.00"}
    )
    assert einfach.status_code == 201

    detail = await client.get(f"/api/rechnungen/{misch['id']}", headers=auth_headers(token))
    assert detail.json()["betrag_brutto"] == "15.77"

    liste = await client.get("/api/rechnungen", headers=auth_headers(token))
    body = liste.json()
    je_id = {e["id"]: e for e in body["eintraege"]}
    assert je_id[misch["id"]]["betrag_brutto"] == detail.json()["betrag_brutto"]
    assert je_id[misch["id"]]["steuergruppen"] == detail.json()["steuergruppen"]
    assert body["summe_netto"] == "113.60"
    assert body["summe_brutto"] == "134.77"
    assert body["summe_offen"] == "134.77"

    genau = await client.get(
        "/api/rechnungen?betrag_von=15.77&betrag_bis=15.77", headers=auth_headers(token)
    )
    assert [e["id"] for e in genau.json()["eintraege"]] == [misch["id"]]
    zu_hoch = await client.get("/api/rechnungen?betrag_von=15.78&betrag_bis=20", headers=auth_headers(token))
    assert zu_hoch.json()["eintraege"] == []
    zu_niedrig = await client.get("/api/rechnungen?betrag_von=10&betrag_bis=15.76", headers=auth_headers(token))
    assert zu_niedrig.json()["eintraege"] == []

    sortiert = await client.get("/api/rechnungen?sort=betrag", headers=auth_headers(token))
    assert [e["id"] for e in sortiert.json()["eintraege"]][0] == misch["id"]


@pytest.mark.asyncio
async def test_csv_export_zeigt_alle_saetze_bei_mischbeleg(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    await _mischbeleg(client, token, kunde)

    resp = await client.get("/api/rechnungen/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200
    zeilen = list(csv.reader(io.StringIO(resp.text), delimiter=";"))
    kopf, zeile = zeilen[0], zeilen[1]
    assert zeile[kopf.index("MwSt-Satz")] == "19.00/7.00"
    assert zeile[kopf.index("Brutto")] == "15.77"


@pytest.mark.asyncio
async def test_position_erbt_satz_des_belegs(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "mwst_satz": "7.00"},
    )
    rechnung_id = resp.json()["id"]
    pos = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Buch", "menge": "2", "einzelpreis": "10"},
    )
    assert pos.status_code == 200
    p = pos.json()["positionen"][0]
    assert (p["steuer_kategorie"], p["steuer_satz"]) == ("S", "7.00")
    assert pos.json()["betrag_brutto"] == "21.40"


# Seit Schritt 3 sind Z/E/AE freigeschaltet, aber nur mit passendem Steuergrund.
_MELDUNG_OHNE_GRUND = {
    "Z": "nur § 12 Abs. 3 UStG",
    "E": "braucht einen Steuergrund",
    "AE": "muss der Steuergrund reverse_charge_13b sein",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("kategorie", ["Z", "E", "AE"])
async def test_gating_kategorie_ohne_grund_422(client, make_mandant, make_user, make_kunde, kategorie):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)

    pos = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "x", "einzelpreis": "1", "steuer_kategorie": kategorie},
    )
    assert pos.status_code == 422
    assert _MELDUNG_OHNE_GRUND[kategorie] in pos.json()["detail"]

    anlegen = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "positionen": [{"beschreibung": "x", "einzelpreis": "1", "steuer_kategorie": kategorie}],
        },
    )
    assert anlegen.status_code == 422

    position_id = rechnung["positionen"][0]["id"]
    patch = await client.patch(
        f"/api/rechnungen/{rechnung['id']}/positionen/{position_id}",
        headers=auth_headers(token),
        json={"steuer_kategorie": kategorie},
    )
    assert patch.status_code == 422
    # Nichts wurde veraendert
    nachher = await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))
    assert nachher.json()["steuergruppen"] == rechnung["steuergruppen"]


@pytest.mark.asyncio
async def test_gating_satz_bei_s_nur_regelsaetze(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)
    url = f"/api/rechnungen/{rechnung['id']}/positionen"

    fuenf = await client.post(
        url, headers=auth_headers(token), json={"beschreibung": "x", "einzelpreis": "1", "steuer_satz": "5"}
    )
    assert fuenf.status_code == 422
    assert "nicht erlaubt" in fuenf.json()["detail"]

    null = await client.post(
        url, headers=auth_headers(token), json={"beschreibung": "x", "einzelpreis": "1", "steuer_satz": "0"}
    )
    assert null.status_code == 422

    # Schema-Validierung: Satz bei Kategorie ohne Satz muss 0 sein.
    z_mit_satz = await client.post(
        url,
        headers=auth_headers(token),
        json={"beschreibung": "x", "einzelpreis": "1", "steuer_kategorie": "Z", "steuer_satz": "7"},
    )
    assert z_mit_satz.status_code == 422

    position_id = rechnung["positionen"][0]["id"]
    patch_fuenf = await client.patch(
        f"/api/rechnungen/{rechnung['id']}/positionen/{position_id}",
        headers=auth_headers(token),
        json={"steuer_satz": "5"},
    )
    assert patch_fuenf.status_code == 422


@pytest.mark.asyncio
async def test_position_steuer_aendern_nur_im_entwurf(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)
    position_id = rechnung["positionen"][0]["id"]
    url = f"/api/rechnungen/{rechnung['id']}/positionen/{position_id}"

    ok = await client.patch(url, headers=auth_headers(token), json={"steuer_satz": "7"})
    assert ok.status_code == 200
    assert [g["satz"] for g in ok.json()["steuergruppen"]] == ["7.00"]
    assert ok.json()["steuergruppen"][0]["netto"] == "13.60"
    assert ok.json()["betrag_brutto"] == "14.55"  # 13,60 + 0,952 -> 0,95

    versand = await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versand.status_code == 200
    gesperrt = await client.patch(url, headers=auth_headers(token), json={"steuer_satz": "19"})
    assert gesperrt.status_code == 400
    nachher = await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))
    assert nachher.json()["betrag_brutto"] == "14.55"


@pytest.mark.asyncio
async def test_kleinunternehmer_positionen_automatisch_e_null(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _mischbeleg(client, token, kunde)
    assert [(p["steuer_kategorie"], p["steuer_satz"]) for p in rechnung["positionen"]] == [
        ("E", "0.00"),
        ("E", "0.00"),
    ]
    assert rechnung["steuergruppen"] == [
        {
            "kategorie": "E",
            "satz": "0.00",
            "netto": "13.60",
            "steuer": "0.00",
            "hinweis": _KU_HINWEIS,
            "hinweise": [_KU_HINWEIS],
        }
    ]
    assert rechnung["betrag_brutto"] == "13.60"

    # Auch explizite Angaben und spaetere Positionen werden erzwungen; das Gating greift hier nicht.
    pos = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "x", "einzelpreis": "10", "steuer_kategorie": "S", "steuer_satz": "19"},
    )
    assert pos.status_code == 200
    assert pos.json()["positionen"][-1]["steuer_kategorie"] == "E"
    assert pos.json()["positionen"][-1]["steuer_satz"] == "0.00"
    assert pos.json()["betrag_brutto"] == "23.60"


@pytest.mark.asyncio
async def test_storno_kopiert_steuerfelder_und_summiert_auf_null(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)
    versand = await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versand.status_code == 200

    storno_resp = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=auth_headers(token))
    assert storno_resp.status_code == 201
    storno = storno_resp.json()

    assert [(p["steuer_kategorie"], p["steuer_satz"], p["einzelpreis"]) for p in storno["positionen"]] == [
        ("S", "19.00", "-10.10"),
        ("S", "7.00", "-3.50"),
    ]
    assert storno["steuergruppen"] == [
        {"kategorie": "S", "satz": "19.00", "netto": "-10.10", "steuer": "-1.92", "hinweis": None, "hinweise": []},
        {"kategorie": "S", "satz": "7.00", "netto": "-3.50", "steuer": "-0.25", "hinweis": None, "hinweise": []},
    ]
    original = (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()
    for feld in ("betrag_netto", "betrag_steuer", "betrag_brutto"):
        assert Decimal(original[feld]) + Decimal(storno[feld]) == 0, feld
    for g_orig, g_storno in zip(original["steuergruppen"], storno["steuergruppen"], strict=True):
        assert Decimal(g_orig["netto"]) + Decimal(g_storno["netto"]) == 0
        assert Decimal(g_orig["steuer"]) + Decimal(g_storno["steuer"]) == 0


# --- PDF / E-Rechnung / Auswertung --------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_und_e_rechnung_fuer_mischbeleg(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten=_FIRMENDATEN_E_RECHNUNG,
        typ="gewerbe",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
    )
    rechnung = await _mischbeleg(client, token, kunde)
    entwurf_pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    assert entwurf_pdf.status_code == 200
    assert entwurf_pdf.content.startswith(b"%PDF")

    versand = await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versand.status_code == 200
    assert versand.json()["xml_object_key"] is not None
    xml = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))
    assert xml.status_code == 200
    assert b">19.00<" in xml.content and b">7.00<" in xml.content
    assert b">15.77<" in xml.content  # Gesamtbetrag aus den Gruppen


@pytest.mark.asyncio
async def test_ust_va_und_datev_je_steuergruppe(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _mischbeleg(client, token, kunde)
    await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )

    ustva = await client.get("/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert ustva.status_code == 200
    saetze = {z["satz"]: z for z in ustva.json()["umsatzsteuer_saetze"]}
    assert (saetze["19.00"]["netto"], saetze["19.00"]["steuer"]) == ("10.10", "1.92")
    assert (saetze["7.00"]["netto"], saetze["7.00"]["steuer"]) == ("3.50", "0.25")
    assert ustva.json()["summe_umsatzsteuer"] == "2.17"

    datev = await client.get(
        "/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert datev.status_code == 200
    zeilen = list(csv.reader(io.StringIO(datev.text), delimiter=";"))[2:]
    assert [(z[0], z[4], z[5]) for z in zeilen] == [("12,02", "8400", "3"), ("3,75", "8300", "2")]


@pytest.mark.asyncio
async def test_kleinunternehmer_ust_va_und_datev_wie_bisher(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde,
        firmendaten={"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"},
    )
    rechnung = await _mischbeleg(client, token, kunde)
    await client.patch(
        f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token), json={"status": "versendet"}
    )

    ustva = await client.get("/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token))
    assert ustva.json()["umsatzsteuer_saetze"] == [
        {"satz": "0.00", "netto": "13.60", "steuer": "0.00"},
    ]
    datev = await client.get(
        "/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    zeilen = list(csv.reader(io.StringIO(datev.text), delimiter=";"))[2:]
    assert [(z[0], z[4], z[5]) for z in zeilen] == [("13,60", "8400", "")]


def test_buchung_ohne_konfiguriertes_konto_bricht_ab_statt_falsch_zu_buchen():
    # Ersetzt den NotImplementedError-Test aus Schritt 2: Z/AE und E ausser
    # Kleinunternehmer haben kein Default-Konto, sondern verlangen die Konfiguration.
    mandant = Mandant(firmendaten={})
    for kategorie in ("Z", "AE", "E"):
        beleg = Rechnung(rechnungsnummer="R-1", betrag_netto=Decimal("0"), mwst_satz=Decimal("19"))
        gruppe = steuer_service.steuer_gruppen(beleg, [_position(1, "10", "0", kategorie)])[0]
        with pytest.raises(KontoNichtKonfiguriert, match=f"Steuerkategorie {kategorie} ist kein Erlöskonto hinterlegt"):
            _erloeskonto(mandant, gruppe)
