"""Organigramm Schritt 1: Migration 0102, Datenmigration, RLS, Registry, Pruef-Logik."""
import asyncio
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text

from app.core.config import get_settings
from app.core.rechte_registry import (
    SCOPE_RANG,
    alle_bereiche,
    aktionen_fuer_bereich,
    ist_gueltig,
    scopes_fuer_bereich,
)
from app.db.session import system_session, tenant_session
from app.models.account_typ import RECHTE_ALLE_AKTIONEN, RECHTE_BEREICHE, AccountTypRecht
from app.models.organigramm import Position, PositionBesetzung
from app.services.organigramm_pruefung_service import organigramm_pruefen
from tests.conftest import auth_headers, login

_BACKEND = os.path.dirname(os.path.dirname(__file__))


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


def _sync_engine():
    return create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)


async def _migrieren(richtung: str, ziel: str) -> None:
    # alembic laeuft synchron; im Thread, damit die Event-Loop des Tests frei bleibt.
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


def _tabellen(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _check_namen(engine, tabelle: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_check_constraints(tabelle)}


async def test_migration_0102_up_down_up():
    engine = _sync_engine()
    neu = {"org_einheiten", "positionen", "position_besetzungen", "position_rechte", "user_rechte"}
    try:
        await _migrieren("downgrade", "0101")
        assert not neu & _tabellen(engine)
        assert {c["name"] for c in inspect(engine).get_columns("account_typ_rechte")}.isdisjoint(
            {"mandant_id", "scope"}
        )
        assert {"ck_account_typ_rechte_bereich_valid", "ck_account_typ_rechte_aktion_valid"} <= _check_namen(
            engine, "account_typ_rechte"
        )

        await _migrieren("upgrade", "head")
        assert neu <= _tabellen(engine)
        spalten = {c["name"]: c for c in inspect(engine).get_columns("account_typ_rechte")}
        assert spalten["mandant_id"]["nullable"] is False
        assert spalten["scope"]["nullable"] is False
        checks = _check_namen(engine, "account_typ_rechte")
        assert "ck_account_typ_rechte_scope_valid" in checks
        assert not {"ck_account_typ_rechte_bereich_valid", "ck_account_typ_rechte_aktion_valid"} & checks
        with engine.connect() as conn:
            for tabelle in (*neu, "account_typ_rechte"):
                relrls, relforce = conn.execute(
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
                    {"t": tabelle},
                ).one()
                assert relrls and relforce, tabelle
                policies = conn.execute(
                    text("SELECT policyname FROM pg_policies WHERE tablename = :t"), {"t": tabelle}
                ).scalars().all()
                assert policies == ["mandant_isolation"], tabelle
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


async def test_downgrade_entfernt_neue_bereiche_und_aktionen(make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker")
    async with system_session() as session:
        session.add(
            AccountTypRecht(
                mandant_id=mandant.id,
                account_typ_id=user.account_typ_id,
                bereich="organigramm",
                aktion="rechte_verwalten",
                erlaubt=True,
            )
        )
    engine = _sync_engine()
    try:
        await _migrieren("downgrade", "0101")
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            assert conn.execute(text("SELECT count(*) FROM account_typ_rechte WHERE bereich = 'organigramm'")).scalar() == 0
            assert conn.execute(text("SELECT count(*) FROM account_typ_rechte")).scalar() > 0
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


_SQL_MANDANT = "INSERT INTO mandanten (id, name, slug) VALUES (:id, :name, :slug)"
_SQL_TYP = (
    "INSERT INTO account_typen (id, mandant_id, name, reihenfolge, nur_zugewiesene_kunden) "
    "VALUES (:id, :m, :name, :r, :nzk)"
)
_SQL_USER = (
    "INSERT INTO users (id, mandant_id, email, password_hash, role, account_typ_id, name, aktiv) "
    "VALUES (:id, :m, :email, 'x', :role, :typ, :name, :aktiv)"
)
_SQL_RECHT = (
    "INSERT INTO account_typ_rechte (id, account_typ_id, bereich, aktion, erlaubt) "
    "VALUES (gen_random_uuid(), :typ, :b, :a, true)"
)


async def test_datenmigration_positionen_besetzungen_scopes():
    engine = _sync_engine()
    ids = {k: uuid.uuid4() for k in ("m1", "m2", "t1", "t2", "t3", "a1", "a2", "u1", "u2", "u3", "u4", "b1")}
    try:
        await _migrieren("downgrade", "0101")
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(text(_SQL_MANDANT), {"id": ids["m1"], "name": "Alpha", "slug": "alpha-" + uuid.uuid4().hex[:6]})
            conn.execute(text(_SQL_MANDANT), {"id": ids["m2"], "name": "Beta", "slug": "beta-" + uuid.uuid4().hex[:6]})
            for key, name, r, nzk in (("t1", "Dispo", 1, False), ("t2", "Techniker", 2, True), ("t3", "Leer", 3, False)):
                conn.execute(text(_SQL_TYP), {"id": ids[key], "m": ids["m1"], "name": name, "r": r, "nzk": nzk})
            for key, m, role, typ, aktiv in (
                ("a1", "m1", "mandant_admin", None, True),
                ("a2", "m1", "mandant_admin", None, False),
                ("b1", "m2", "mandant_admin", None, True),
                ("u1", "m1", "custom", "t1", True),
                ("u2", "m1", "custom", "t1", True),
                ("u3", "m1", "custom", "t2", True),
                ("u4", "m1", "custom", "t1", False),
            ):
                conn.execute(
                    text(_SQL_USER),
                    {
                        "id": ids[key],
                        "m": ids[m],
                        "email": f"{key}-{uuid.uuid4().hex[:6]}@example.de",
                        "role": role,
                        "typ": ids[typ] if typ else None,
                        "name": key.upper(),
                        "aktiv": aktiv,
                    },
                )
            for typ, bereich, aktion in (
                ("t1", "vorgaenge", "sehen"),
                ("t1", "material", "sehen"),
                ("t1", "projekte", "zeitplan_sehen"),
                ("t2", "vorgaenge", "sehen"),
                ("t2", "kunden", "sehen"),
                ("t2", "material", "sehen"),
            ):
                conn.execute(text(_SQL_RECHT), {"typ": ids[typ], "b": bereich, "a": aktion})

        await _migrieren("upgrade", "head")

        async with system_session() as session:
            positionen = (await session.execute(select(Position))).scalars().all()
            je_mandant = {m: [p for p in positionen if p.mandant_id == ids[m]] for m in ("m1", "m2")}
            assert len(je_mandant["m1"]) == 4  # Wurzel + 3 Account-Typen
            assert len(je_mandant["m2"]) == 1
            wurzel = next(p for p in je_mandant["m1"] if p.parent_id is None)
            assert wurzel.titel == "Geschäftsführung" and wurzel.account_typ_id is None and wurzel.typ == "linie"
            assert wurzel.soll_besetzung == 1
            nach_typ = {p.account_typ_id: p for p in je_mandant["m1"] if p.account_typ_id}
            assert all(p.parent_id == wurzel.id for p in nach_typ.values())
            assert nach_typ[ids["t1"]].titel == "Dispo"
            assert nach_typ[ids["t1"]].soll_besetzung == 2
            assert nach_typ[ids["t2"]].soll_besetzung == 1
            assert nach_typ[ids["t3"]].soll_besetzung == 1

            besetzungen = (await session.execute(select(PositionBesetzung))).scalars().all()
            sitzt_auf = {b.user_id: b.position_id for b in besetzungen}
            assert sitzt_auf[ids["a1"]] == wurzel.id
            assert ids["a2"] not in sitzt_auf and ids["u4"] not in sitzt_auf  # inaktive ausgelassen
            assert sitzt_auf[ids["u1"]] == sitzt_auf[ids["u2"]] == nach_typ[ids["t1"]].id
            assert sitzt_auf[ids["u3"]] == nach_typ[ids["t2"]].id
            assert all(b.gueltig_bis is None and b.art == "regulaer" for b in besetzungen)
            assert not [b for b in besetzungen if b.position_id == nach_typ[ids["t3"]].id]
            m2_wurzel = je_mandant["m2"][0]
            assert sitzt_auf[ids["b1"]] == m2_wurzel.id

            rechte = (await session.execute(select(AccountTypRecht))).scalars().all()
            scope = {(r.account_typ_id, r.bereich): r.scope for r in rechte}
            assert scope[(ids["t2"], "vorgaenge")] == "eigene"
            assert scope[(ids["t2"], "kunden")] == "eigene"
            assert scope[(ids["t2"], "material")] == "mandant"  # Registry kennt dort nur mandant
            assert all(r.scope == "mandant" for r in rechte if r.account_typ_id == ids["t1"])
            assert all(r.mandant_id == ids["m1"] for r in rechte)

            ergebnis = await organigramm_pruefen(session)
            assert ergebnis.abweichungen == []
            alpha = next(m for m in ergebnis.mandanten if m.mandant_id == ids["m1"])
            assert alpha.nutzer_geprueft == 4  # a1, u1, u2, u3
            assert alpha.positionen == 4 and alpha.besetzungen == 4
            nur_beta = await organigramm_pruefen(session, mandant_id=ids["m2"])
            assert [m.mandant_id for m in nur_beta.mandanten] == [ids["m2"]]

            # Pruefung schlaegt an: Besetzung entfernen -> (a) und (c) verletzt.
            b_u3 = next(b for b in besetzungen if b.user_id == ids["u3"])
            async with session.begin_nested() as sp:
                await session.delete(b_u3)
                await session.flush()
                kaputt = await organigramm_pruefen(session, mandant_id=ids["m1"])
                await sp.rollback()
            assert any("u3-" in a and "0 aktive Besetzungen" in a for a in kaputt.abweichungen)
            assert any("u3-" in a and "Rechte-Matrix weicht ab" in a for a in kaputt.abweichungen)
    finally:
        await _migrieren("upgrade", "head")
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            conn.execute(text("TRUNCATE users, mandanten RESTART IDENTITY CASCADE"))
        engine.dispose()


async def test_rls_mandant_b_sieht_nichts_von_a(make_mandant, make_user):
    a = await make_mandant(name="MandantA")
    b = await make_mandant(name="MandantB")
    user = await make_user(mandant=a, role="techniker")
    async with system_session() as session:
        pos = Position(mandant_id=a.id, titel="Wurzel A")
        session.add(pos)
        await session.flush()
        session.add(PositionBesetzung(mandant_id=a.id, position_id=pos.id, user_id=user.id))

    async with tenant_session(mandant_id=a.id, is_super_admin=False) as session:
        assert len((await session.execute(select(Position))).scalars().all()) == 1
        assert len((await session.execute(select(PositionBesetzung))).scalars().all()) == 1
        assert len((await session.execute(select(AccountTypRecht))).scalars().all()) > 0

    async with tenant_session(mandant_id=b.id, is_super_admin=False) as session:
        assert (await session.execute(select(Position))).scalars().all() == []
        assert (await session.execute(select(PositionBesetzung))).scalars().all() == []
        assert (await session.execute(select(AccountTypRecht))).scalars().all() == []


async def test_db_werte_sind_teilmenge_der_registry(make_mandant, make_user):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="techniker")
    await make_user(mandant=mandant, role="disponent")
    async with system_session() as session:
        paare = (await session.execute(select(AccountTypRecht.bereich, AccountTypRecht.aktion).distinct())).all()
    assert paare
    for bereich, aktion in paare:
        assert ist_gueltig(bereich, aktion), (bereich, aktion)


def test_registry_struktur():
    keys = [b.key for b in alle_bereiche()]
    assert len(keys) == len(set(keys))
    assert "organigramm" in keys and set(RECHTE_BEREICHE) == set(keys)
    for b in alle_bereiche():
        assert aktionen_fuer_bereich(b.key) == b.aktionen
        assert list(b.scopes) == sorted(b.scopes, key=SCOPE_RANG.__getitem__)
        assert b.scopes[-1] == "mandant"
    voll = ("eigene", "team", "teilbaum", "bereich", "mandant")
    for key in ("vorgaenge", "kunden", "dispo", "projekte", "mitarbeiterverwaltung", "organigramm"):
        assert scopes_fuer_bereich(key) == voll
    for key in ("material", "abrechnung", "statistik", "formulare", "partner", "fehlerberichte"):
        assert scopes_fuer_bereich(key) == ("mandant",)
    assert ist_gueltig("abrechnung", "freigeben") and not ist_gueltig("vorgaenge", "freigeben")
    assert ist_gueltig("organigramm", "rechte_verwalten") and ist_gueltig("mitarbeiterverwaltung", "rechte_verwalten")
    assert ist_gueltig("projekte", "zeitplan_beantragen") and not ist_gueltig("vorgaenge", "zeitplan_sehen")
    assert ist_gueltig("fehlerberichte", "freigeben") and ist_gueltig("vorgaenge", "exportieren")
    assert not ist_gueltig("unbekannt", "sehen")
    assert {"zeitplan_sehen", "exportieren", "freigeben", "rechte_verwalten"} <= set(RECHTE_ALLE_AKTIONEN)


async def test_registry_endpoint_und_me_matrix(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    assert (await client.get("/api/rechte/registry")).status_code == 401
    resp = await client.get("/api/rechte/registry", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    bereiche = {b["key"]: b for b in body["bereiche"]}
    assert "organigramm" in bereiche
    assert bereiche["organigramm"]["scopes"] == body["scopes"] == ["eigene", "team", "teilbaum", "bereich", "mandant"]
    assert "rechte_verwalten" in bereiche["organigramm"]["aktionen"]
    assert bereiche["material"]["scopes"] == ["mandant"]
    assert bereiche["kunden"]["modul"] == "kundenverwaltung"

    me = await client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200
    assert "rechte_verwalten" in me.json()["rechte"]["organigramm"]
    assert "freigeben" in me.json()["rechte"]["abrechnung"]


async def test_account_typ_recht_setzen_validiert_gegen_registry(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    h = auth_headers(token)
    typ = (await client.post("/api/account-typen", json={"name": "Neu"}, headers=h)).json()
    url = f"/api/account-typen/{typ['id']}/rechte"

    ok = await client.put(url, json={"bereich": "organigramm", "aktion": "exportieren", "erlaubt": True}, headers=h)
    assert ok.status_code == 200
    assert {"bereich": "organigramm", "aktion": "exportieren", "erlaubt": True} in ok.json()
    for bereich, aktion in (("vorgaenge", "freigeben"), ("unbekannt", "sehen"), ("vorgaenge", "unbekannt")):
        resp = await client.put(url, json={"bereich": bereich, "aktion": aktion, "erlaubt": True}, headers=h)
        assert resp.status_code == 422, (bereich, aktion)

    async with system_session() as session:
        zeile = (
            await session.execute(
                select(AccountTypRecht).where(AccountTypRecht.account_typ_id == uuid.UUID(typ["id"]))
            )
        ).scalar_one()
        assert zeile.mandant_id == mandant.id and zeile.scope == "mandant"


async def test_account_typ_loeschen_entfernt_position_und_haengt_kinder_um(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    typ = (await client.post("/api/account-typen", json={"name": "Weg"}, headers=h)).json()
    typ_id = uuid.UUID(typ["id"])
    async with system_session() as session:
        wurzel = Position(mandant_id=mandant.id, titel="Wurzel")
        session.add(wurzel)
        await session.flush()
        pos = Position(mandant_id=mandant.id, titel="Weg", parent_id=wurzel.id, account_typ_id=typ_id)
        session.add(pos)
        await session.flush()
        kind = Position(mandant_id=mandant.id, titel="Kind", parent_id=pos.id)
        session.add(kind)
        await session.flush()
        wurzel_id, kind_id = wurzel.id, kind.id

    assert (await client.delete(f"/api/account-typen/{typ['id']}", headers=h)).status_code == 204
    async with system_session() as session:
        assert (await session.execute(select(Position).where(Position.account_typ_id == typ_id))).first() is None
        assert (await session.get(Position, kind_id)).parent_id == wurzel_id
