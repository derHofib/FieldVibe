"""Getrennte Abrechnung von Stunden und km einer Zeitbuchung (Migration 0097),
eigener Fahrzeit-Satz und das Backfill der Migration."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import system_session
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.zeiterfassung import Zeiterfassung
from app.models.zeiterfassung_aenderung import ZeiterfassungAenderung
from tests.conftest import _BACKEND_DIR, auth_headers, login
from tests.test_rechnungen_sammelrechnung import _svs, _uebernehmen


async def _zeile(
    *, mandant, vorgang, techniker, kategorie="auftrag", stunden=2.0, km="20.0", lv_position_id=None,
    status="gebucht",
) -> Zeiterfassung:
    start = datetime.now(timezone.utc)
    async with system_session() as session:
        eintrag = Zeiterfassung(
            mandant_id=mandant.id,
            vorgang_id=vorgang.id,
            techniker_id=techniker.id,
            start_at=start,
            ende_at=start + timedelta(hours=stunden),
            kategorie=kategorie,
            abrechenbar=True,
            buchungsstatus=status,
            km=Decimal(km) if km is not None else None,
            lv_position_id=lv_position_id,
        )
        session.add(eintrag)
        await session.flush()
        await session.refresh(eintrag)
        return eintrag


async def _lade(zeile_id) -> Zeiterfassung:
    async with system_session() as session:
        return await session.get(Zeiterfassung, zeile_id)


async def _aktionen(zeile_id) -> list[str]:
    async with system_session() as session:
        return list(
            (
                await session.execute(
                    select(ZeiterfassungAenderung.aktion).where(ZeiterfassungAenderung.zeiterfassung_id == zeile_id)
                )
            ).scalars()
        )


async def _setup(client, make_mandant, make_user, make_kunde, make_vorgang, **einstellungen):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")
    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"fahrzeit_abrechnung": "zeit_und_km", "km_satz_netto": "0.30", **einstellungen},
    )
    assert resp.status_code == 200, resp.text
    return mandant, admin, kunde, vorgang, token


async def _rechnung(client, token, kunde, vorgang) -> str:
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _vorschlaege(client, token, rechnung_id) -> dict:
    resp = await client.get(f"/api/rechnungen/{rechnung_id}/positionsvorschlaege", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return {(v["quelle"], v["lv_position_id"]): v for v in resp.json()}


async def _position(client, token, rechnung_id, quelle, menge="1", einheit="Std", lv_position_id=None) -> dict:
    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={
            "beschreibung": quelle, "menge": menge, "einheit": einheit, "einzelpreis": "0",
            "quelle": quelle, "lv_position_id": lv_position_id,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _positions_id(rechnung: dict, quelle: str, nr: int = 0) -> str:
    return [p["id"] for p in rechnung["positionen"] if p["quelle"] == quelle][nr]


@pytest.mark.asyncio
async def test_nur_zeit_uebernehmen_km_bleibt_offen_und_spaeter_separat(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "zeit", "2")

    z = await _lade(zeile.id)
    assert z.buchungsstatus == "abgerechnet" and str(z.abgerechnet_rechnung_id) == r1
    assert z.km_abgerechnet_rechnung_id is None

    r2 = await _rechnung(client, token, kunde, vorgang)
    vorschlaege = await _vorschlaege(client, token, r2)
    assert ("zeit", None) not in vorschlaege
    assert vorschlaege[("fahrtkosten", None)]["menge"] == "20.0"

    await _position(client, token, r2, "fahrtkosten", "20", "km")
    z = await _lade(zeile.id)
    assert str(z.km_abgerechnet_rechnung_id) == r2
    # Stunden-Verweis bleibt unberuehrt bei der ersten Rechnung
    assert str(z.abgerechnet_rechnung_id) == r1 and z.buchungsstatus == "abgerechnet"
    assert "km_abgerechnet" in await _aktionen(zeile.id)
    # Nichts mehr offen
    r3 = await _rechnung(client, token, kunde, vorgang)
    assert await _vorschlaege(client, token, r3) == {}


@pytest.mark.asyncio
async def test_nur_km_uebernehmen_stunden_bleiben_offen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin, kategorie="fahrzeit")
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "fahrtkosten", "20", "km")

    z = await _lade(zeile.id)
    assert z.buchungsstatus == "gebucht" and z.abgerechnet_rechnung_id is None
    assert str(z.km_abgerechnet_rechnung_id) == r1

    r2 = await _rechnung(client, token, kunde, vorgang)
    vorschlaege = await _vorschlaege(client, token, r2)
    assert ("fahrtkosten", None) not in vorschlaege
    assert vorschlaege[("fahrzeit", None)]["menge"] == "2.00"
    await _position(client, token, r2, "fahrzeit", "2")
    z = await _lade(zeile.id)
    assert z.buchungsstatus == "abgerechnet" and str(z.abgerechnet_rechnung_id) == r2
    assert str(z.km_abgerechnet_rechnung_id) == r1


@pytest.mark.asyncio
async def test_zeile_gesperrt_sobald_ein_anteil_abgerechnet(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)

    # nur km abgerechnet: Stunden 'gebucht' -> Buchung darf nicht storniert, Zeile nicht geaendert/geloescht werden
    nur_km = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "fahrtkosten", "20", "km")
    storno = await client.post(
        "/api/zeiterfassung/buchung-stornieren", headers=headers, json={"ids": [str(nur_km.id)], "grund": "Test"}
    )
    assert storno.status_code == 400 and "km bereits abgerechnet" in storno.text
    assert (await _lade(nur_km.id)).buchungsstatus == "gebucht"
    patch = await client.patch(f"/api/zeiterfassung/{nur_km.id}", headers=headers, json={"taetigkeit": "x"})
    assert patch.status_code == 409
    assert (await client.delete(f"/api/zeiterfassung/{nur_km.id}", headers=headers)).status_code == 409

    # nur Stunden abgerechnet
    nur_zeit = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin, km=None)
    await _position(client, token, r1, "zeit", "2")
    patch = await client.patch(f"/api/zeiterfassung/{nur_zeit.id}", headers=headers, json={"taetigkeit": "x"})
    assert patch.status_code == 409
    assert (await client.delete(f"/api/zeiterfassung/{nur_zeit.id}", headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_zeile_wieder_bearbeitbar_wenn_km_position_entfernt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    rechnung = await _position(client, token, r1, "fahrtkosten", "20", "km")
    resp = await client.delete(
        f"/api/rechnungen/{r1}/positionen/{_positions_id(rechnung, 'fahrtkosten')}", headers=headers
    )
    assert resp.status_code == 200
    z = await _lade(zeile.id)
    assert z.km_abgerechnet_rechnung_id is None and z.buchungsstatus == "gebucht"
    assert "km_abrechnung_zurueckgesetzt" in await _aktionen(zeile.id)
    storno = await client.post(
        "/api/zeiterfassung/buchung-stornieren", headers=headers, json={"ids": [str(zeile.id)], "grund": "Test"}
    )
    assert storno.status_code == 200, storno.text


@pytest.mark.asyncio
async def test_gleiche_quelle_geschwister_erst_bei_letzter_position_frei(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "fahrtkosten", "10", "km")
    rechnung = await _position(client, token, r1, "fahrtkosten", "10", "km")
    erste, zweite = _positions_id(rechnung, "fahrtkosten", 0), _positions_id(rechnung, "fahrtkosten", 1)

    await client.delete(f"/api/rechnungen/{r1}/positionen/{erste}", headers=headers)
    assert str(( await _lade(zeile.id)).km_abgerechnet_rechnung_id) == r1
    await client.delete(f"/api/rechnungen/{r1}/positionen/{zweite}", headers=headers)
    assert (await _lade(zeile.id)).km_abgerechnet_rechnung_id is None


@pytest.mark.asyncio
async def test_loeschen_restore_und_storno_pro_anteil(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_headers = auth_headers(await login(client, operativ.email, "pw-123456"))

    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    # Stunden auf R1, km auf R2 (beide Entwuerfe)
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "zeit", "2")
    r2 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r2, "fahrtkosten", "20", "km")

    # R2 (km) in den Papierkorb: Stunden bleiben bei R1, km sind offen
    assert (await client.delete(f"/api/rechnungen/{r2}", headers=headers)).status_code == 204
    z = await _lade(zeile.id)
    assert z.buchungsstatus == "abgerechnet" and str(z.abgerechnet_rechnung_id) == r1
    r3 = await _rechnung(client, token, kunde, vorgang)
    assert (await _vorschlaege(client, token, r3))[("fahrtkosten", None)]["menge"] == "20.0"
    # Zeile gilt trotz freigegebenem km weiter als gesperrt (Stunden abgerechnet), aber nicht wegen km
    assert not await _km_gesperrt(zeile.id)

    # Wiederherstellen: km wieder gesperrt, kein Vorschlag mehr
    resp = await client.post(f"/api/papierkorb/rechnung/{r2}/wiederherstellen", headers=op_headers)
    assert resp.status_code in (200, 204), resp.text
    assert await _km_gesperrt(zeile.id)
    assert ("fahrtkosten", None) not in await _vorschlaege(client, token, r3)
    aktionen = await _aktionen(zeile.id)
    assert aktionen.count("km_abgerechnet") == 2 and aktionen.count("km_abrechnung_zurueckgesetzt") == 1

    # zwischenzeitlich anderer Rechnung zugeordnet: Restore sperrt sie nicht doppelt
    assert (await client.delete(f"/api/rechnungen/{r2}", headers=headers)).status_code == 204
    await _position(client, token, r3, "fahrtkosten", "20", "km")
    assert str((await _lade(zeile.id)).km_abgerechnet_rechnung_id) == r3
    await client.post(f"/api/papierkorb/rechnung/{r2}/wiederherstellen", headers=op_headers)
    assert str((await _lade(zeile.id)).km_abgerechnet_rechnung_id) == r3

    # Storno einer versendeten Rechnung mit km: Verweis wird geleert, Stunden unberuehrt
    assert (
        await client.patch(f"/api/rechnungen/{r3}", headers=headers, json={"status": "versendet"})
    ).status_code == 200
    assert (await client.post(f"/api/rechnungen/{r3}/storno", headers=headers)).status_code == 201
    z = await _lade(zeile.id)
    assert z.km_abgerechnet_rechnung_id is None
    assert z.buchungsstatus == "abgerechnet" and str(z.abgerechnet_rechnung_id) == r1


async def _km_gesperrt(zeile_id) -> bool:
    from app.services.rechnung_service import km_gesperrt

    async with system_session() as session:
        return await km_gesperrt(session, await session.get(Zeiterfassung, zeile_id))


@pytest.mark.asyncio
async def test_purge_entwurf_loest_km_verweis(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_headers = auth_headers(await login(client, operativ.email, "pw-123456"))
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    await _position(client, token, r1, "fahrtkosten", "20", "km")
    await client.delete(f"/api/rechnungen/{r1}", headers=auth_headers(token))
    assert (await client.delete(f"/api/papierkorb/rechnung/{r1}", headers=op_headers)).status_code == 204
    assert (await _lade(zeile.id)).km_abgerechnet_rechnung_id is None


@pytest.mark.asyncio
async def test_svs_leistung_und_km_derselben_zeile_getrennt(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        svs_id = (await _svs(session, mandant)).id
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin, lv_position_id=svs_id, km="10.0")
    r1 = await _rechnung(client, token, kunde, vorgang)
    vorschlaege = await _vorschlaege(client, token, r1)
    assert vorschlaege[("leistung", str(svs_id))]["menge"] == "2.00"
    assert vorschlaege[("fahrtkosten", None)]["menge"] == "10.0"

    rechnung = await _position(client, token, r1, "leistung", "2", lv_position_id=str(svs_id))
    z = await _lade(zeile.id)
    assert z.buchungsstatus == "abgerechnet" and z.km_abgerechnet_rechnung_id is None
    assert ("fahrtkosten", None) in await _vorschlaege(client, token, await _rechnung(client, token, kunde, vorgang))

    await _position(client, token, r1, "fahrtkosten", "10", "km")
    assert str((await _lade(zeile.id)).km_abgerechnet_rechnung_id) == r1

    # Leistung entfernen: nur Stunden frei, km bleiben
    await client.delete(
        f"/api/rechnungen/{r1}/positionen/{_positions_id(rechnung, 'leistung')}", headers=auth_headers(token)
    )
    z = await _lade(zeile.id)
    assert z.buchungsstatus == "gebucht" and str(z.km_abgerechnet_rechnung_id) == r1


@pytest.mark.asyncio
async def test_vorgang_uebernehmen_waehlt_anteile_getrennt(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    zeile = await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin)
    r1 = await _rechnung(client, token, kunde, vorgang)
    resp = await _uebernehmen(client, token, r1, vorgang, stundensatz="50", nur=lambda v: v["quelle"] == "zeit")
    assert resp.status_code in (200, 201), resp.text
    z = await _lade(zeile.id)
    assert z.buchungsstatus == "abgerechnet" and z.km_abgerechnet_rechnung_id is None
    resp = await client.get(
        f"/api/rechnungen/{r1}/vorgaenge/{vorgang.id}/vorschlaege", headers=auth_headers(token)
    )
    assert [v["quelle"] for v in resp.json()] == ["fahrtkosten"]


@pytest.mark.asyncio
async def test_fahrzeit_satz_im_vorschlag_und_in_uebernahme(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, vorgang, token = await _setup(
        client, make_mandant, make_user, make_kunde, make_vorgang, fahrzeit_satz_netto="55.50"
    )
    headers = auth_headers(token)
    einstellungen = (await client.get("/api/mandant/einstellungen", headers=headers)).json()
    assert einstellungen["fahrzeit_satz_netto"] == "55.50"

    await _zeile(mandant=mandant, vorgang=vorgang, techniker=admin, kategorie="fahrzeit", stunden=1.5)
    r1 = await _rechnung(client, token, kunde, vorgang)
    vorschlaege = await _vorschlaege(client, token, r1)
    assert vorschlaege[("fahrzeit", None)]["einzelpreis"] == "55.50"
    assert vorschlaege[("fahrtkosten", None)]["einzelpreis"] == "0.30"

    resp = await _uebernehmen(client, token, r1, vorgang, nur=lambda v: v["quelle"] == "fahrzeit")
    assert resp.status_code in (200, 201), resp.text
    async with system_session() as session:
        pos = (await session.execute(select(RechnungPosition).where(RechnungPosition.quelle == "fahrzeit"))).scalar_one()
        assert pos.einzelpreis == Decimal("55.50")

    # zuruecksetzen auf None -> Preis 0; negativ wird abgelehnt
    resp = await client.patch("/api/mandant/einstellungen", headers=headers, json={"fahrzeit_satz_netto": None})
    assert resp.status_code == 200 and resp.json()["fahrzeit_satz_netto"] is None
    resp = await client.patch("/api/mandant/einstellungen", headers=headers, json={"fahrzeit_satz_netto": "-1"})
    assert resp.status_code == 422


# --- Migration 0097: Backfill und up/down/up ----------------------------------------------


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    return cfg


async def _alt_zustand(mandant, kunde, admin, v1, v2):
    """Zeilen im Alt-Zustand (vor 0097: eine abgerechnete Zeile zeigt nur ueber
    abgerechnet_rechnung_id auf die Rechnung, km_abgerechnet_rechnung_id noch NULL)."""
    async with system_session() as session:
        svs = await _svs(session, mandant)

        async def rechnung(vorgang_id, nr, positionen):
            r = Rechnung(
                mandant_id=mandant.id, kunde_id=kunde.id, vorgang_id=vorgang_id,
                rechnungsnummer=f"R-{nr}", betrag_netto=Decimal("0"), erstellt_von=admin.id,
            )
            session.add(r)
            await session.flush()
            for i, (quelle, pos_vorgang, lv) in enumerate(positionen, 1):
                session.add(
                    RechnungPosition(
                        mandant_id=mandant.id, rechnung_id=r.id, position=i, beschreibung=quelle,
                        menge=Decimal("1"), einheit="Std", einzelpreis=Decimal("0"), quelle=quelle,
                        vorgang_id=pos_vorgang, lv_position_id=lv,
                    )
                )
            await session.flush()
            return r.id

        def zeile(vorgang_id, rechnung_id, kategorie="auftrag", km="10.0", lv=None):
            start = datetime.now(timezone.utc)
            z = Zeiterfassung(
                mandant_id=mandant.id, vorgang_id=vorgang_id, techniker_id=admin.id, start_at=start,
                ende_at=start + timedelta(hours=1), kategorie=kategorie, abrechenbar=True,
                buchungsstatus="abgerechnet", abgerechnet_rechnung_id=rechnung_id,
                km=Decimal(km) if km else None, lv_position_id=lv,
            )
            session.add(z)
            return z

        r_nur_fk = await rechnung(v1.id, 1, [("fahrtkosten", v1.id, None)])
        r_zeit_fk = await rechnung(v1.id, 2, [("zeit", v1.id, None), ("fahrtkosten", v1.id, None)])
        r_nur_zeit = await rechnung(v1.id, 3, [("zeit", v1.id, None)])
        r_svs_fk = await rechnung(v1.id, 4, [("leistung", v1.id, svs.id), ("fahrtkosten", v1.id, None)])
        r_alt = await rechnung(v1.id, 5, [("fahrtkosten", None, None)])  # Altposition ohne vorgang_id
        r_sammel = await rechnung(None, 6, [("fahrtkosten", v2.id, None), ("zeit", v1.id, None)])
        r_ohne_km = await rechnung(v1.id, 7, [("fahrtkosten", v1.id, None)])

        zeilen = {
            "nur_fahrtkosten": zeile(v1.id, r_nur_fk, kategorie="fahrzeit"),
            "zeit_und_fk": zeile(v1.id, r_zeit_fk),
            "nur_zeit": zeile(v1.id, r_nur_zeit),
            "svs_und_fk": zeile(v1.id, r_svs_fk, lv=svs.id),
            "ohne_lv_nur_fk": zeile(v1.id, r_svs_fk),
            "altposition": zeile(v1.id, r_alt),
            "sammel_anderer_vorgang": zeile(v1.id, r_sammel),
            "ohne_km": zeile(v1.id, r_ohne_km, km=None),
        }
        await session.flush()
        ids = {k: z.id for k, z in zeilen.items()}
        rechnungen = {
            "nur_fahrtkosten": r_nur_fk, "zeit_und_fk": r_zeit_fk, "nur_zeit": r_nur_zeit,
            "svs_und_fk": r_svs_fk, "ohne_lv_nur_fk": r_svs_fk, "altposition": r_alt,
            "sammel_anderer_vorgang": r_sammel, "ohne_km": r_ohne_km,
        }
        return ids, rechnungen


def _zeilen_sql(engine, ids):
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
        rows = conn.execute(
            sqlalchemy.text(
                "SELECT id, buchungsstatus, abgerechnet_rechnung_id FROM zeiterfassung WHERE id = ANY(:ids)"
            ),
            {"ids": list(ids.values())},
        ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


@pytest.mark.asyncio
async def test_migration_0097_backfill_und_up_down_up(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    v1 = await make_vorgang(mandant=mandant, kunde=kunde)
    v2 = await make_vorgang(mandant=mandant, kunde=kunde)
    ids, rechnungen = await _alt_zustand(mandant, kunde, admin, v1, v2)

    cfg = _cfg()
    engine = sqlalchemy.create_engine(get_settings().database_url_sync)
    command.downgrade(cfg, "0096")
    try:
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("SELECT set_config('app.is_super_admin', 'true', true)"))
            rows = {
                r[0]: r[1:]
                for r in conn.execute(
                    sqlalchemy.text(
                        "SELECT id, buchungsstatus, abgerechnet_rechnung_id, km_abgerechnet_rechnung_id "
                        "FROM zeiterfassung WHERE id = ANY(:ids)"
                    ),
                    {"ids": list(ids.values())},
                ).all()
            }

        def ergebnis(name):
            return rows[ids[name]]

        # nur fahrtkosten-Position: km gesperrt, Stunden wieder offen
        assert ergebnis("nur_fahrtkosten") == ("gebucht", None, rechnungen["nur_fahrtkosten"])
        # Stunden- UND km-Position: beides bleibt
        assert ergebnis("zeit_und_fk") == ("abgerechnet", rechnungen["zeit_und_fk"], rechnungen["zeit_und_fk"])
        # nur Stunden-Position: km nicht abgerechnet -> ab jetzt offen
        assert ergebnis("nur_zeit") == ("abgerechnet", rechnungen["nur_zeit"], None)
        # SVS-Zeile hat leistung-Position, die Zeile ohne LV nicht
        assert ergebnis("svs_und_fk") == ("abgerechnet", rechnungen["svs_und_fk"], rechnungen["svs_und_fk"])
        assert ergebnis("ohne_lv_nur_fk") == ("gebucht", None, rechnungen["ohne_lv_nur_fk"])
        # Altposition ohne vorgang_id: Vorgang kommt von der Rechnung
        assert ergebnis("altposition") == ("gebucht", None, rechnungen["altposition"])
        # fahrtkosten-Position gehoert zu anderem Vorgang der Sammelrechnung
        assert ergebnis("sammel_anderer_vorgang") == ("abgerechnet", rechnungen["sammel_anderer_vorgang"], None)
        # Zeile ohne km bleibt unberuehrt
        assert ergebnis("ohne_km") == ("abgerechnet", rechnungen["ohne_km"], None)

        # down: km-Sperre geht zurueck in die gekoppelte Sperre
        command.downgrade(cfg, "0096")
        zurueck = _zeilen_sql(engine, ids)
        assert zurueck[ids["nur_fahrtkosten"]] == ("abgerechnet", rechnungen["nur_fahrtkosten"])
        assert zurueck[ids["zeit_und_fk"]] == ("abgerechnet", rechnungen["zeit_und_fk"])
        assert zurueck[ids["nur_zeit"]] == ("abgerechnet", rechnungen["nur_zeit"])
        assert zurueck[ids["ohne_lv_nur_fk"]] == ("abgerechnet", rechnungen["ohne_lv_nur_fk"])

        # und wieder hoch: Backfill ist auf dem gekoppelten Zustand wiederholbar
        command.upgrade(cfg, "head")
        wieder = _zeilen_sql(engine, ids)
        assert wieder[ids["nur_fahrtkosten"]] == ("gebucht", None)
        assert wieder[ids["nur_zeit"]] == ("abgerechnet", rechnungen["nur_zeit"])
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
