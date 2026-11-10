"""Rechte-Engine (app/services/berechtigung_service.py) -- Aufloesung, Scopes, Baum-Helfer."""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.api.deps import get_db, require_recht
from app.core.rechte_registry import alle_bereiche
from app.core.security import hash_password
from app.db.session import engine, system_session
from app.main import app as haupt_app
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.organigramm import (
    OrgEinheit,
    Position,
    PositionBesetzung,
    PositionRecht,
    UserRecht,
)
from app.models.user import User
from app.services import berechtigung_service as bs
from app.services.organigramm_sync_service import wurzel_position
from tests.conftest import login

JETZT = lambda: datetime.now(timezone.utc)  # noqa: E731


async def _typ(session, mandant, name, rechte=(), **felder) -> AccountTyp:
    """rechte: (bereich, aktion) oder (bereich, aktion, scope)."""
    typ = AccountTyp(mandant_id=mandant.id, name=name, **felder)
    session.add(typ)
    await session.flush()
    for eintrag in rechte:
        bereich, aktion, *rest = eintrag
        session.add(
            AccountTypRecht(
                mandant_id=mandant.id,
                account_typ_id=typ.id,
                bereich=bereich,
                aktion=aktion,
                erlaubt=True,
                scope=rest[0] if rest else "mandant",
            )
        )
    await session.flush()
    return typ


async def _pos(session, mandant, titel, *, parent=None, typ=None, **felder) -> Position:
    position = Position(
        mandant_id=mandant.id,
        titel=titel,
        parent_id=parent.id if parent else None,
        account_typ_id=typ.id if typ else None,
        **felder,
    )
    session.add(position)
    await session.flush()
    return position


async def _user(session, mandant, name="U") -> User:
    user = User(
        mandant_id=mandant.id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.de",
        password_hash=hash_password("pw-123456"),
        role="custom",
        name=name,
    )
    session.add(user)
    await session.flush()
    return user


async def _besetze(session, mandant, position, user, **felder) -> PositionBesetzung:
    felder.setdefault("gueltig_von", JETZT() - timedelta(days=1))
    besetzung = PositionBesetzung(mandant_id=mandant.id, position_id=position.id, user_id=user.id, **felder)
    session.add(besetzung)
    await session.flush()
    return besetzung


async def _override(session, mandant, ziel, bereich, aktion, wirkung, scope=None):
    modell = PositionRecht if isinstance(ziel, Position) else UserRecht
    schluessel = {"position_id": ziel.id} if isinstance(ziel, Position) else {"user_id": ziel.id}
    session.add(
        modell(mandant_id=mandant.id, bereich=bereich, aktion=aktion, wirkung=wirkung, scope=scope, **schluessel)
    )
    await session.flush()


async def _rechte(session, user) -> bs.EffektiveRechte:
    return await bs.effektive_rechte(session, user_id=user.id, rolle="custom")


async def test_typ_basis_mit_scope_und_herkunft(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(
            session, mandant, "Disponent", [("vorgaenge", "sehen"), ("kunden", "sehen", "eigene")]
        )
        # erlaubt=false zaehlt nicht
        session.add(
            AccountTypRecht(
                mandant_id=mandant.id, account_typ_id=typ.id, bereich="material", aktion="sehen", erlaubt=False
            )
        )
        pos = await _pos(session, mandant, "Disponent", typ=typ)
        user = await _user(session, mandant)
        await _besetze(session, mandant, pos, user)

        rechte = await _rechte(session, user)
        assert rechte.hat("vorgaenge", "sehen") and rechte.scope("vorgaenge", "sehen") == "mandant"
        assert rechte.scope("kunden", "sehen") == "eigene"
        assert not rechte.hat("material", "sehen")
        assert not rechte.hat("vorgaenge", "loeschen")
        recht = rechte.rechte[("vorgaenge", "sehen")]
        assert recht.herkunft == (
            {"art": "account_typ", "position_id": str(pos.id), "account_typ_id": str(typ.id)},
        )
        assert rechte.gewaehrende_positionen[("vorgaenge", "sehen")] == {pos.id: "mandant"}
        assert rechte.als_matrix()["vorgaenge"] == ["sehen"]
        assert rechte.als_scopes()["kunden"] == {"sehen": "eigene"}


async def test_positions_override_erlauben_erweitert_scope_und_fuegt_hinzu(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(session, mandant, "Techniker", [("kunden", "sehen", "eigene")])
        pos = await _pos(session, mandant, "Teamleiter", typ=typ)
        user = await _user(session, mandant)
        await _besetze(session, mandant, pos, user)
        await _override(session, mandant, pos, "kunden", "sehen", "erlauben", "teilbaum")
        await _override(session, mandant, pos, "material", "sehen", "erlauben")  # scope None, keine Basis

        rechte = await _rechte(session, user)
        assert rechte.scope("kunden", "sehen") == "teilbaum"
        assert rechte.scope("material", "sehen") == "mandant"
        arten = [h["art"] for h in rechte.rechte[("kunden", "sehen")].herkunft]
        assert arten == ["account_typ", "position_override"]
        assert [h["art"] for h in rechte.rechte[("material", "sehen")].herkunft] == ["position_override"]


async def test_override_erlauben_kann_scope_nicht_verkleinern(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(session, mandant, "T", [("kunden", "sehen", "bereich")])
        pos = await _pos(session, mandant, "P", typ=typ)
        user = await _user(session, mandant)
        await _besetze(session, mandant, pos, user)
        await _override(session, mandant, pos, "kunden", "sehen", "erlauben", "eigene")
        assert (await _rechte(session, user)).scope("kunden", "sehen") == "bereich"


async def test_positions_verweigern_wirkt_nur_lokal(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ_a = await _typ(session, mandant, "A", [("material", "sehen"), ("vorgaenge", "sehen")])
        typ_b = await _typ(session, mandant, "B", [("material", "sehen")])
        pos_a = await _pos(session, mandant, "Pos A", typ=typ_a)
        pos_b = await _pos(session, mandant, "Pos B", typ=typ_b)
        user = await _user(session, mandant)
        await _besetze(session, mandant, pos_a, user)
        await _override(session, mandant, pos_a, "material", "sehen", "verweigern")

        nur_a = await _rechte(session, user)
        assert not nur_a.hat("material", "sehen")
        assert nur_a.hat("vorgaenge", "sehen")
        assert nur_a.verweigert[("material", "sehen")][0]["art"] == "position_override"

        await _besetze(session, mandant, pos_b, user)
        beide = await _rechte(session, user)
        assert beide.hat("material", "sehen")
        herkunft = beide.rechte[("material", "sehen")].herkunft
        assert [h["position_id"] for h in herkunft] == [str(pos_b.id)]
        assert beide.gewaehrende_positionen[("material", "sehen")] == {pos_b.id: "mandant"}


async def test_user_verweigern_gilt_global_und_user_erlauben_fuegt_hinzu(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ_a = await _typ(session, mandant, "A", [("material", "sehen")])
        typ_b = await _typ(session, mandant, "B", [("material", "sehen"), ("statistik", "sehen")])
        user = await _user(session, mandant)
        for titel, typ in (("Pos A", typ_a), ("Pos B", typ_b)):
            await _besetze(session, mandant, await _pos(session, mandant, titel, typ=typ), user)
        await _override(session, mandant, user, "material", "sehen", "verweigern")
        await _override(session, mandant, user, "formulare", "bearbeiten", "erlauben", "mandant")

        rechte = await _rechte(session, user)
        assert not rechte.hat("material", "sehen")
        assert rechte.hat("statistik", "sehen")
        assert rechte.hat("formulare", "bearbeiten")
        assert rechte.rechte[("formulare", "bearbeiten")].herkunft == ({"art": "user_override", "wirkung": "erlauben"},)
        assert rechte.verweigert[("material", "sehen")] == [{"art": "user_override", "wirkung": "verweigern"}]


async def test_scope_vereinigung_groesster_gewinnt_mit_herkunft(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ_a = await _typ(session, mandant, "A", [("vorgaenge", "sehen", "team")])
        typ_b = await _typ(session, mandant, "B", [("vorgaenge", "sehen", "bereich")])
        typ_c = await _typ(session, mandant, "C", [("vorgaenge", "sehen", "eigene")])
        user = await _user(session, mandant)
        positionen = []
        for titel, typ in (("A", typ_a), ("B", typ_b), ("C", typ_c)):
            positionen.append(await _pos(session, mandant, titel, typ=typ))
            await _besetze(session, mandant, positionen[-1], user)

        rechte = await _rechte(session, user)
        assert rechte.scope("vorgaenge", "sehen") == "bereich"
        assert len(rechte.rechte[("vorgaenge", "sehen")].herkunft) == 3
        assert rechte.gewaehrende_positionen[("vorgaenge", "sehen")] == {
            positionen[0].id: "team",
            positionen[1].id: "bereich",
            positionen[2].id: "eigene",
        }


async def test_vertretung_und_besetzung_nur_im_zeitfenster(make_mandant):
    mandant = await make_mandant()
    jetzt = JETZT()
    async with system_session() as session:
        typ = await _typ(session, mandant, "Chef", [("abrechnung", "sehen")])
        pos = await _pos(session, mandant, "Chef", typ=typ)
        zukunft = await _user(session, mandant, "Z")
        vergangen = await _user(session, mandant, "V")
        aktuell = await _user(session, mandant, "A")
        offen = await _user(session, mandant, "O")
        await _besetze(
            session, mandant, pos, zukunft, art="vertretung",
            gueltig_von=jetzt + timedelta(days=1), gueltig_bis=jetzt + timedelta(days=5),
        )
        await _besetze(
            session, mandant, pos, vergangen, art="vertretung",
            gueltig_von=jetzt - timedelta(days=5), gueltig_bis=jetzt - timedelta(days=1),
        )
        await _besetze(
            session, mandant, pos, aktuell, art="vertretung",
            gueltig_von=jetzt - timedelta(days=1), gueltig_bis=jetzt + timedelta(days=1),
        )
        await _besetze(session, mandant, pos, offen)

        assert not (await _rechte(session, zukunft)).hat("abrechnung", "sehen")
        assert not (await _rechte(session, vergangen)).hat("abrechnung", "sehen")
        assert (await _rechte(session, aktuell)).hat("abrechnung", "sehen")
        assert (await _rechte(session, offen)).hat("abrechnung", "sehen")
        # Stichtag: mitten in der kuenftigen Vertretung
        spaeter = await bs.effektive_rechte(
            session, user_id=zukunft.id, rolle="custom", stichtag=jetzt + timedelta(days=2)
        )
        assert spaeter.hat("abrechnung", "sehen")


async def test_ohne_besetzung_keine_rechte_auch_nicht_ueber_user_override(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(session, mandant, "Vorlage", [("vorgaenge", "sehen")])
        await _pos(session, mandant, "Geplante Stelle", typ=typ, geplant=True)
        await _pos(session, mandant, "Vakant", typ=typ)
        user = await _user(session, mandant)
        await _override(session, mandant, user, "material", "sehen", "erlauben")
        rechte = await _rechte(session, user)
        assert rechte.rechte == {} and rechte.aktive_position_ids == ()
        assert rechte.als_matrix() == {b.key: [] for b in alle_bereiche()}
        # beendete Besetzung zaehlt ebenfalls nicht
        pos = await _pos(session, mandant, "Ehemalige", typ=typ)
        await _besetze(
            session, mandant, pos, user,
            gueltig_von=JETZT() - timedelta(days=3), gueltig_bis=JETZT() - timedelta(days=1),
        )
        assert (await _rechte(session, user)).rechte == {}


async def test_archivierte_und_abgelaufene_position_gibt_nichts(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(session, mandant, "T", [("vorgaenge", "sehen")])
        user = await _user(session, mandant)
        heute = date.today()
        for felder in (
            {"archiviert_am": JETZT() - timedelta(hours=1)},
            {"gueltig_bis": heute - timedelta(days=1)},
            {"gueltig_ab": heute + timedelta(days=1)},
        ):
            pos = await _pos(session, mandant, f"P{len(felder)}{list(felder)[0]}", typ=typ, **felder)
            await _besetze(session, mandant, pos, user)
        assert (await _rechte(session, user)).rechte == {}
        # Grenzfall: gueltig_bis heute ist noch gueltig
        pos = await _pos(session, mandant, "Heute", typ=typ, gueltig_ab=heute, gueltig_bis=heute)
        await _besetze(session, mandant, pos, user)
        assert (await _rechte(session, user)).hat("vorgaenge", "sehen")


@pytest.mark.parametrize("rolle", ["super_admin", "mandant_admin", "loesch_operativ", "loesch_ansicht", "disponent"])
async def test_nicht_custom_rollen_haben_alle_rechte(make_mandant, rolle):
    mandant = await make_mandant()
    async with system_session() as session:
        user = await _user(session, mandant)
        rechte = await bs.effektive_rechte(session, user_id=user.id, rolle=rolle)
        assert rechte.alle_rechte
        for b in alle_bereiche():
            for aktion in b.aktionen:
                assert rechte.hat(b.key, aktion) and rechte.scope(b.key, aktion) == "mandant"
        assert rechte.rechte[("vorgaenge", "sehen")].herkunft == ({"art": "rolle", "rolle": rolle},)
        assert rechte.als_matrix() == {b.key: list(b.aktionen) for b in alle_bereiche()}
        assert rechte.flag(bs.FLAG_ZEITEN_BUCHEN)
        assert not await bs.ist_auf_zugewiesene_kunden_beschraenkt(session, user_id=user.id, rolle=rolle)
        assert await bs.user_ids_fuer_recht(session, SimpleNamespace(user_id=user.id, role=rolle), "vorgaenge", "sehen") is None


async def test_stabsstelle_teilbaum(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        gf = await wurzel_position(session, mandant.id)
        qm = await _pos(session, mandant, "QM", parent=gf)
        qm.typ = "stabsstelle"
        assistenz = await _pos(session, mandant, "QM-Assistenz", parent=qm)  # typ linie
        abteilung = await _pos(session, mandant, "Abteilung", parent=gf)
        mitarbeiter = await _pos(session, mandant, "Mitarbeiter", parent=abteilung)
        verschachtelt = await _pos(session, mandant, "QM-Stab", parent=qm)
        verschachtelt.typ = "stabsstelle"
        await session.flush()

        assert await bs.teilbaum_position_ids(session, gf.id) == {gf.id, abteilung.id, mitarbeiter.id}
        assert await bs.teilbaum_position_ids(session, qm.id) == {qm.id, assistenz.id}
        assert await bs.teilbaum_position_ids(session, assistenz.id) == {assistenz.id}
        assert await bs.teilbaum_position_ids(session, verschachtelt.id) == {verschachtelt.id}


async def test_user_ids_fuer_scope(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        gf = await wurzel_position(session, mandant.id)
        bereich = OrgEinheit(mandant_id=mandant.id, name="Technik", typ="bereich")
        session.add(bereich)
        await session.flush()
        team_a = OrgEinheit(mandant_id=mandant.id, name="Team A", typ="team", parent_id=bereich.id)
        team_b = OrgEinheit(mandant_id=mandant.id, name="Team B", typ="team", parent_id=bereich.id)
        fremd = OrgEinheit(mandant_id=mandant.id, name="Verwaltung", typ="bereich")
        session.add_all([team_a, team_b, fremd])
        await session.flush()

        leiter = await _pos(session, mandant, "Technikleiter", parent=gf, org_einheit_id=bereich.id)
        lead_a = await _pos(session, mandant, "Lead A", parent=leiter, org_einheit_id=team_a.id)
        tech_a = await _pos(session, mandant, "Tech A", parent=lead_a, org_einheit_id=team_a.id)
        tech_a2 = await _pos(session, mandant, "Tech A2", parent=lead_a, org_einheit_id=team_a.id)
        tech_b = await _pos(session, mandant, "Tech B", parent=leiter, org_einheit_id=team_b.id)
        buero = await _pos(session, mandant, "Buero", parent=gf, org_einheit_id=fremd.id)
        # Geschwister ohne Einheit
        ohne_1 = await _pos(session, mandant, "Ohne 1", parent=gf)
        ohne_2 = await _pos(session, mandant, "Ohne 2", parent=gf)

        user = {}
        for name, pos in (
            ("leiter", leiter), ("lead_a", lead_a), ("tech_a", tech_a), ("tech_a2", tech_a2),
            ("tech_b", tech_b), ("buero", buero), ("ohne_1", ohne_1), ("ohne_2", ohne_2),
        ):
            user[name] = await _user(session, mandant, name)
            await _besetze(session, mandant, pos, user[name])
        # Beendete Besetzung zaehlt nicht
        ehemalig = await _user(session, mandant, "ehemalig")
        await _besetze(
            session, mandant, tech_a, ehemalig,
            gueltig_von=JETZT() - timedelta(days=4), gueltig_bis=JETZT() - timedelta(days=1),
        )

        ids = lambda *namen: {user[n].id for n in namen}  # noqa: E731

        assert await bs.user_ids_fuer_scope(session, [tech_a.id], "mandant") is None
        assert await bs.user_ids_fuer_scope(session, [tech_a.id], "eigene", user_id=user["tech_a"].id) == ids("tech_a")
        # team: gleiche Einheit
        assert await bs.user_ids_fuer_scope(session, [tech_a.id], "team", user_id=user["tech_a"].id) == ids(
            "lead_a", "tech_a", "tech_a2"
        )
        # team ohne Einheit: gleiche Elternposition (Geschwister mit Einheit zaehlen nicht)
        assert await bs.user_ids_fuer_scope(session, [ohne_1.id], "team", user_id=user["ohne_1"].id) == ids(
            "ohne_1", "ohne_2"
        )
        # teilbaum umfasst Team + alles darunter
        assert await bs.user_ids_fuer_scope(session, [lead_a.id], "teilbaum", user_id=user["lead_a"].id) == ids(
            "lead_a", "tech_a", "tech_a2"
        )
        assert await bs.user_ids_fuer_scope(session, [leiter.id], "teilbaum", user_id=user["leiter"].id) == ids(
            "leiter", "lead_a", "tech_a", "tech_a2", "tech_b"
        )
        # bereich: oberste Bereichs-Einheit und alles darunter, auch von einer Teamposition aus
        assert await bs.user_ids_fuer_scope(session, [tech_a.id], "bereich", user_id=user["tech_a"].id) == ids(
            "leiter", "lead_a", "tech_a", "tech_a2", "tech_b"
        )
        # Position ohne Einheit: kein Bereich -> bereich entspricht team + teilbaum
        assert await bs.user_ids_fuer_scope(session, [ohne_1.id], "bereich", user_id=user["ohne_1"].id) == ids(
            "ohne_1", "ohne_2"
        )


async def test_user_ids_fuer_recht_vereinigt_scopes_je_position(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        gf = await wurzel_position(session, mandant.id)
        typ_team = await _typ(session, mandant, "TypTeam", [("vorgaenge", "sehen", "teilbaum")])
        typ_eigene = await _typ(session, mandant, "TypEigene", [("vorgaenge", "sehen", "eigene")])
        chef = await _pos(session, mandant, "Chef", parent=gf, typ=typ_team)
        unter = await _pos(session, mandant, "Unter", parent=chef)
        sonst = await _pos(session, mandant, "Sonst", parent=gf, typ=typ_eigene)
        u_chef, u_unter = await _user(session, mandant, "chef"), await _user(session, mandant, "unter")
        await _besetze(session, mandant, chef, u_chef)
        await _besetze(session, mandant, sonst, u_chef)
        await _besetze(session, mandant, unter, u_unter)
        auth = SimpleNamespace(user_id=u_chef.id, role="custom")

        assert await bs.user_ids_fuer_recht(session, auth, "vorgaenge", "sehen") == {u_chef.id, u_unter.id}
        assert await bs.user_ids_fuer_recht(session, auth, "kunden", "sehen") == set()


async def test_flags_ueber_aktive_positionen_vereinigt_und_nur_zugewiesene_kunden(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        buchen = await _typ(session, mandant, "Buchen", [], darf_zeiten_buchen=True)
        eingeschraenkt = await _typ(
            session, mandant, "Eingeschraenkt", [("kunden", "sehen", "eigene")], nur_zugewiesene_kunden=True
        )
        frei = await _typ(session, mandant, "Frei", [("kunden", "sehen")])
        flag_ohne_scope = await _typ(session, mandant, "FlagOhneScope", [("kunden", "sehen")], nur_zugewiesene_kunden=True)
        ohne_besetzung = await _user(session, mandant, "O")
        einer = await _user(session, mandant, "E")
        gemischt = await _user(session, mandant, "G")
        fail_safe = await _user(session, mandant, "F")
        await _besetze(session, mandant, await _pos(session, mandant, "B", typ=buchen), einer)
        await _besetze(session, mandant, await _pos(session, mandant, "E", typ=eingeschraenkt), einer)
        await _besetze(session, mandant, await _pos(session, mandant, "E2", typ=eingeschraenkt), gemischt)
        await _besetze(session, mandant, await _pos(session, mandant, "F", typ=frei), gemischt)
        await _besetze(session, mandant, await _pos(session, mandant, "X", typ=flag_ohne_scope), fail_safe)

        async def beschraenkt(u):
            return await bs.ist_auf_zugewiesene_kunden_beschraenkt(session, user_id=u.id, rolle="custom")

        assert not (await _rechte(session, ohne_besetzung)).flag(bs.FLAG_ZEITEN_BUCHEN)
        assert (await _rechte(session, einer)).flag(bs.FLAG_ZEITEN_BUCHEN)
        assert not (await _rechte(session, einer)).flag(bs.FLAG_ABWESENHEITEN_VERWALTEN)
        assert await beschraenkt(einer)  # Scope eigene
        assert not await beschraenkt(gemischt)  # frei gewinnt (groesster Scope)
        assert await beschraenkt(fail_safe)  # Flag ohne umgesetzten Scope bleibt beschraenkt
        assert not await beschraenkt(ohne_besetzung)


async def test_aufloesung_pro_session_nur_einmal_gecacht(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        typ = await _typ(session, mandant, "T", [("vorgaenge", "sehen"), ("kunden", "sehen")])
        user = await _user(session, mandant)
        await _besetze(session, mandant, await _pos(session, mandant, "P", typ=typ), user)
        auth = SimpleNamespace(user_id=user.id, role="custom")

        statements: list[str] = []

        def zaehlen(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", zaehlen)
        try:
            await bs.hat_recht(session, auth, "vorgaenge", "sehen")
            nach_erstem = len(statements)
            assert nach_erstem > 0
            await bs.hat_recht(session, auth, "kunden", "sehen")
            await bs.scope_von(session, auth, "kunden", "sehen")
            await bs.ist_auf_zugewiesene_kunden_beschraenkt(session, user_id=user.id, rolle="custom")
            assert len(statements) == nach_erstem
            bs.cache_leeren(session)
            await bs.hat_recht(session, auth, "vorgaenge", "sehen")
            assert len(statements) == 2 * nach_erstem
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", zaehlen)


async def test_mehrere_require_recht_je_request_loesen_nur_einmal_auf(make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    mini = FastAPI()

    @mini.get(
        "/probe",
        dependencies=[
            Depends(require_recht("vorgaenge", "sehen")),
            Depends(require_recht("kunden", "sehen")),
            Depends(require_recht("dispo", "sehen")),
        ],
    )
    async def probe(session=Depends(get_db)):
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=haupt_app), base_url="http://test") as client:
        token = await login(client, user.email, "pw-123456")

    statements: list[str] = []

    def zaehlen(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", zaehlen)
    try:
        async with AsyncClient(transport=ASGITransport(app=mini), base_url="http://test") as client:
            antwort = await client.get("/probe", headers={"Authorization": f"Bearer {token}"})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", zaehlen)
    assert antwort.status_code == 200
    # Aufloesung = Besetzungen, Typen, Typ-Rechte, Positions-Overrides, User-Overrides.
    aufloesungen = [s for s in statements if "FROM position_besetzungen" in s]
    assert len(aufloesungen) == 1
    assert len([s for s in statements if "FROM account_typ_rechte" in s]) == 1
