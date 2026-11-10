"""Golden-Test: Die Rechte-Engine (Besetzungen im Organigramm) liefert fuer
typische Konstellationen exakt dasselbe wie die bisherige Berechnung ueber
users.account_typ_id (rechte_service ohne user_id = Altpfad als Referenz)."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.rechte_registry import alle_bereiche
from app.db.session import system_session
from app.models.account_typ import RECHTE_BEREICHE, aktionen_fuer_bereich
from app.services import rechte_service
from app.services.organigramm_pruefung_service import organigramm_pruefen
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _alte_matrix(session, *, role, account_typ_id) -> dict[str, set[str]]:
    """Altberechnung von /me.rechte (vor der Engine)."""
    if role == "custom" and account_typ_id is not None:
        matrix = await rechte_service.rechte_matrix_fuer_account_typ(session, account_typ_id)
        return {b: {a for a, erlaubt in aktionen.items() if erlaubt} for b, aktionen in matrix.items()}
    return {b: set(aktionen_fuer_bereich(b)) for b in RECHTE_BEREICHE}


async def _konstellation(client, make_mandant, make_user):
    mandant = await make_mandant("Golden")
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW, email="admin@golden.de")
    token = await login(client, admin.email, PW)
    kopf = auth_headers(token)

    # Frei definierte Typen ueber die API (Sync: Position je Typ, Scope aus Flag).
    for name, flags, rechte in (
        (
            "Vollzugriff-Zeit",
            {"darf_zeiten_buchen": True, "darf_abwesenheiten_verwalten": True, "darf_vorgaenge_selbst_uebernehmen": True},
            [("projekte", "zeitplan_sehen"), ("projekte", "zeitplan_beantragen"), ("abrechnung", "freigeben"),
             ("mitarbeiterverwaltung", "bearbeiten"), ("kunden", "sehen"), ("vorgaenge", "sehen")],
        ),
        (
            "Eingeschraenkt",
            {"nur_zugewiesene_kunden": True},
            [("kunden", "sehen"), ("vorgaenge", "sehen"), ("vorgaenge", "bearbeiten"), ("material", "sehen")],
        ),
        ("Ohne Rechte", {}, []),
    ):
        angelegt = await client.post("/api/account-typen", headers=kopf, json={"name": name, **flags})
        assert angelegt.status_code == 201, angelegt.text
        for bereich, aktion in rechte:
            r = await client.put(
                f"/api/account-typen/{angelegt.json()['id']}/rechte",
                headers=kopf,
                json={"bereich": bereich, "aktion": aktion, "erlaubt": True},
            )
            assert r.status_code == 200, r.text

    users = {
        "admin": admin,
        "techniker": await make_user(mandant=mandant, role="techniker", password=PW),
        "disponent": await make_user(mandant=mandant, role="disponent", password=PW),
        "controller": await make_user(mandant=mandant, role="controller", password=PW),
        "mitarbeiter": await make_user(mandant=mandant, role="mitarbeiter", password=PW),
        "loesch_ansicht": await make_user(mandant=mandant, role="loesch_ansicht", password=PW),
        "loesch_operativ": await make_user(mandant=mandant, role="loesch_operativ", password=PW),
        "super_admin": await make_user(mandant=None, role="super_admin", password=PW),
    }
    typen = {t["name"]: t["id"] for t in (await client.get("/api/account-typen", headers=kopf)).json()}
    for name in ("Vollzugriff-Zeit", "Eingeschraenkt", "Ohne Rechte"):
        angelegt = await client.post(
            "/api/users",
            headers=kopf,
            json={
                "mandant_id": str(mandant.id), "email": f"{name.split()[0].lower()}@golden.de", "password": "supersecret1",
                "role": "custom", "account_typ_id": typen[name], "name": name,
            },
        )
        assert angelegt.status_code == 201, angelegt.text
        users[name] = angelegt.json()
    return mandant, users


@pytest.mark.asyncio
async def test_me_matrix_und_rechte_service_vor_und_nach_der_umstellung_identisch(client, make_mandant, make_user):
    mandant, users = await _konstellation(client, make_mandant, make_user)
    geprueft = 0
    for name, user in users.items():
        email = user["email"] if isinstance(user, dict) else user.email
        passwort = "supersecret1" if isinstance(user, dict) else PW
        token = await login(client, email, passwort)
        me = (await client.get("/api/auth/me", headers=auth_headers(token))).json()
        role, typ_id = me["role"], me["account_typ_id"]

        async with system_session() as session:
            from uuid import UUID

            typ_uuid = UUID(typ_id) if typ_id else None
            alt = await _alte_matrix(session, role=role, account_typ_id=typ_uuid)
            assert {b: set(a) for b, a in me["rechte"].items()} == alt, name
            assert set(me["rechte"]) == {b.key for b in alle_bereiche()}

            kw = {"role": role, "account_typ_id": typ_uuid}
            assert me["nur_zugewiesene_kunden"] == await rechte_service.ist_auf_zugewiesene_kunden_beschraenkt(session, **kw), name
            assert me["darf_vorgaenge_selbst_uebernehmen"] == await rechte_service.darf_vorgang_selbst_uebernehmen(session, **kw), name
            assert me["darf_zeiten_buchen"] == await rechte_service.darf_zeiten_buchen(session, **kw), name
            assert me["darf_abwesenheiten_verwalten"] == await rechte_service.darf_abwesenheiten_verwalten(session, **kw), name

            # Engine-Pfad der rechte_service-Funktionen (user_id) == Altpfad
            from uuid import UUID as _U

            uid = _U(me["id"])
            neu = {**kw, "user_id": uid}
            assert await rechte_service.ist_auf_zugewiesene_kunden_beschraenkt(session, **neu) == me["nur_zugewiesene_kunden"]
            assert await rechte_service.darf_vorgang_selbst_uebernehmen(session, **neu) == me["darf_vorgaenge_selbst_uebernehmen"]
            assert await rechte_service.darf_zeiten_buchen(session, **neu) == me["darf_zeiten_buchen"]
            assert await rechte_service.darf_abwesenheiten_verwalten(session, **neu) == me["darf_abwesenheiten_verwalten"]
            assert await rechte_service.darf_fremde_mitarbeiterdaten_einsehen(
                session, **neu
            ) == await rechte_service.darf_fremde_mitarbeiterdaten_einsehen(session, **kw), name
            for bereich in RECHTE_BEREICHE:
                for aktion in aktionen_fuer_bereich(bereich):
                    erwartet = True if role != "custom" else await rechte_service.hat_recht(
                        session, account_typ_id=typ_uuid, bereich=bereich, aktion=aktion
                    )
                    assert (aktion in me["rechte"][bereich]) == erwartet, (name, bereich, aktion)
                    assert await rechte_service.hat_recht(
                        session, account_typ_id=typ_uuid, bereich=bereich, aktion=aktion, user_id=uid, role=role
                    ) == erwartet, (name, bereich, aktion)
            # Scopes: neues Feld, Rollen ohne Matrix -> mandant, Rest konsistent zur Matrix
            for bereich, aktionen in me["rechte"].items():
                for aktion in aktionen:
                    assert me["rechte_scopes"][bereich][aktion] in {"eigene", "team", "teilbaum", "bereich", "mandant"}
        geprueft += 1
    assert geprueft == len(users)

    # Eingeschraenkt: Flag -> Scope eigene (nur Bereiche mit "eigene"), sonst mandant
    token = await login(client, users["Eingeschraenkt"]["email"], "supersecret1")
    scopes = (await client.get("/api/auth/me", headers=auth_headers(token))).json()["rechte_scopes"]
    assert scopes["kunden"]["sehen"] == "eigene" and scopes["vorgaenge"]["sehen"] == "eigene"
    assert scopes["material"]["sehen"] == "mandant"

    async with system_session() as session:
        ergebnis = await organigramm_pruefen(session, mandant_id=mandant.id)
        assert ergebnis.abweichungen == []
        assert ergebnis.mandanten[0].nutzer_geprueft >= 5


@pytest.mark.asyncio
async def test_flag_nur_zugewiesene_kunden_wird_in_scope_uebersetzt_und_zurueck(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kopf = auth_headers(await login(client, admin.email, PW))
    typ = (await client.post("/api/account-typen", headers=kopf, json={"name": "Aussendienst"})).json()
    for bereich, aktion in (("kunden", "sehen"), ("material", "sehen"), ("dispo", "sehen")):
        await client.put(
            f"/api/account-typen/{typ['id']}/rechte", headers=kopf, json={"bereich": bereich, "aktion": aktion, "erlaubt": True}
        )
    user = (
        await client.post(
            "/api/users",
            headers=kopf,
            json={"mandant_id": str(mandant.id), "email": "a@x.de", "password": "supersecret1", "role": "custom",
                  "account_typ_id": typ["id"], "name": "A"},
        )
    ).json()

    async def me():
        token = await login(client, "a@x.de", "supersecret1")
        return (await client.get("/api/auth/me", headers=auth_headers(token))).json()

    zustand = await me()
    assert zustand["nur_zugewiesene_kunden"] is False
    assert zustand["rechte_scopes"]["kunden"]["sehen"] == "mandant"

    await client.patch(f"/api/account-typen/{typ['id']}", headers=kopf, json={"nur_zugewiesene_kunden": True})
    zustand = await me()
    assert zustand["nur_zugewiesene_kunden"] is True
    assert zustand["rechte_scopes"]["kunden"]["sehen"] == "eigene"
    assert zustand["rechte_scopes"]["dispo"]["sehen"] == "eigene"
    assert zustand["rechte_scopes"]["material"]["sehen"] == "mandant"  # Bereich kennt eigene nicht

    # Erneutes Setzen auf denselben Wert laesst fein eingestellte Scopes in Ruhe
    async with system_session() as session:
        from sqlalchemy import update

        from app.models.account_typ import AccountTypRecht

        await session.execute(
            update(AccountTypRecht)
            .where(AccountTypRecht.account_typ_id == typ["id"], AccountTypRecht.bereich == "dispo")
            .values(scope="team")
        )
    await client.patch(f"/api/account-typen/{typ['id']}", headers=kopf, json={"nur_zugewiesene_kunden": True, "name": "Aussendienst 2"})
    assert (await me())["rechte_scopes"]["dispo"]["sehen"] == "team"

    # Neues Recht bei gesetztem Flag startet mit Scope eigene
    await client.put(
        f"/api/account-typen/{typ['id']}/rechte", headers=kopf, json={"bereich": "vorgaenge", "aktion": "sehen", "erlaubt": True}
    )
    assert (await me())["rechte_scopes"]["vorgaenge"]["sehen"] == "eigene"

    await client.patch(f"/api/account-typen/{typ['id']}", headers=kopf, json={"nur_zugewiesene_kunden": False})
    zustand = await me()
    assert zustand["nur_zugewiesene_kunden"] is False
    assert zustand["rechte_scopes"]["kunden"]["sehen"] == "mandant"
    assert user["account_typ_id"] == typ["id"]
