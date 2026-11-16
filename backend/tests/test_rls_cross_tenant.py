"""Generischer Cross-Tenant-Test: ein Mandant-A-Admin ruft ueber die echte API
alle GET-Endpunkte auf (aus der OpenAPI-Route-Tabelle abgeleitet, nicht von Hand
gepflegt) und darf nirgends eine ID oder Daten von Mandant B sehen. Neue
GET-Endpunkte werden automatisch mitgetestet; nur begruendete Ausnahmen stehen
in der Liste unten."""

import json
import re
import uuid
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app.db.session import system_session
from app.main import app
from tests.conftest import auth_headers, login

# Keine sinnvolle Mandanten-Pruefung moeglich bzw. eigene Authentifizierung.
AUSNAHMEN_EXAKT: dict[str, str] = {
    "/health": "oeffentlich, keine Mandantendaten",
    "/health/ready": "oeffentlich, keine Mandantendaten",
    "/health/heartbeats": "Worker-Zustand, keine Mandantendaten",
    "/healthz": "oeffentlich, keine Mandantendaten",
    "/api/stream": "SSE-Stream mit Ticket-Auth, endet nicht von selbst",
    "/api/public/rechtliches": "oeffentlich ohne Login; Mandant nur per Portal-Slug",
    "/api/admin/dsgvo-dokumente/{typ}/download-url": "nicht-UUID-Parameter (Enum), plattformweite Dokumente",
    "/api/import/vorlagen/{dateiname}": "nicht-UUID-Parameter (Dateiname), statische Vorlagen",
}
# Pfadpraefixe mit eigenem Auth-Mechanismus, den ein Mandanten-Admin nicht besitzt
# (Kundenportal-/Partnerportal-Token bzw. Service-Token).
AUSNAHMEN_PRAEFIX: dict[str, str] = {
    "/api/kundenportal/": "Portal-Auth (Kundenportal-Token); mit Staff-Token 401/403",
    "/api/partnerportal/": "Portal-Auth (Partner-Token); mit Staff-Token 401/403",
    "/api/service/": "Service-Token-Auth, kein Mandantenbezug",
}
# Nicht-UUID-Pfadparameter, fuer die der Test selbst einen B-Wert einsetzt.
# Wert: (Tabelle, Spalte).
STRING_PARAMETER: dict[str, tuple[str, str]] = {"qr_code": ("anlagen", "qr_code")}

# Bekannte, bewusst gemeldete Leaks: Pfad -> Begruendung/Beleg (xfail statt Fehler).
BEKANNTE_LECKS: dict[str, str] = {}

MARKER = "LEAKMARKER-B"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _ausgenommen(pfad: str) -> str | None:
    if pfad in AUSNAHMEN_EXAKT:
        return AUSNAHMEN_EXAKT[pfad]
    for praefix, grund in AUSNAHMEN_PRAEFIX.items():
        if pfad.startswith(praefix):
            return grund
    return None


def _get_endpunkte() -> list[tuple[str, list[tuple[str, str]]]]:
    """(Pfad, [(Parametername, Typ/Format)]) aller GET-Routen. Ueber das
    OpenAPI-Schema statt app.routes, weil FastAPI includierte Router dort
    verschachtelt haelt; das Schema ist die oeffentliche, flache Sicht."""
    ergebnis = []
    for pfad, ops in app.openapi()["paths"].items():
        op = ops.get("get")
        if op is None:
            continue
        params = [
            (p["name"], p["schema"].get("format") or p["schema"].get("type", "string"))
            for p in op.get("parameters", [])
            if p["in"] == "path"
        ]
        ergebnis.append((pfad, params))
    return ergebnis


def _norm(name: str) -> str:
    n = name.lower().replace("_id", "").replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return n.replace("_", "")


def _passt(param: str, tabelle: str) -> bool:
    """Heuristik: Parametername (vorgang_id) und Tabellenname (vorgaenge) teilen
    nach Umlaut-Normalisierung ein Praefix von mind. 5 Zeichen."""
    a, b = _norm(param), _norm(tabelle)
    gemeinsam = 0
    for x, y in zip(a, b):
        if x != y:
            break
        gemeinsam += 1
    return gemeinsam >= min(5, len(a))


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


async def _insert(session, tabelle: str, **spalten) -> uuid.UUID:
    werte = []
    for k, v in list(spalten.items()):
        if isinstance(v, dict):
            spalten[k] = json.dumps(v)
            werte.append(f"CAST(:{k} AS jsonb)")
        else:
            werte.append(f":{k}")
    row = await session.execute(
        text(f"INSERT INTO {tabelle} ({', '.join(spalten)}) VALUES ({', '.join(werte)}) RETURNING id"),
        spalten,
    )
    return row.scalar_one()


async def _b_daten_anlegen(mandant_b, user_b, kunde, vorgang, anlage) -> None:
    """Legt in Mandant B moeglichst viele verschiedene Entitaeten an (direkt per
    SQL, die Spalten-Defaults der Tabellen fuellen den Rest)."""
    m = mandant_b.id
    u = user_b.id
    heute = date(2026, 1, 15)
    async with system_session(grund="test") as s:
        await s.execute(text("UPDATE anlagen SET qr_code = :q WHERE id = :i"), {"q": f"QR-{MARKER}", "i": anlage.id})
        await _insert(s, "standorte", mandant_id=m, kunde_id=kunde.id, bezeichnung=f"Standort {MARKER}", adresse={"ort": MARKER})
        mat = await _insert(s, "material", mandant_id=m, bezeichnung=f"Material {MARKER}")
        await _insert(s, "lieferanten", mandant_id=m, name=f"Lieferant {MARKER}")
        await _insert(s, "material_bedarfe", mandant_id=m, material_id=mat, vorgang_id=vorgang.id, menge=3, erstellt_von=u)
        angebot = await _insert(s, "angebote", mandant_id=m, kunde_id=kunde.id, angebotsnummer=f"A-{MARKER}", erstellt_von=u)
        await _insert(s, "angebot_positionen", mandant_id=m, angebot_id=angebot, position=1, beschreibung=MARKER, einzelpreis=10)
        rechnung = await _insert(s, "rechnungen", mandant_id=m, kunde_id=kunde.id, rechnungsnummer=f"R-{MARKER}", betrag_netto=100, erstellt_von=u)
        await _insert(s, "rechnung_positionen", mandant_id=m, rechnung_id=rechnung, position=1, beschreibung=MARKER, einzelpreis=100, steuer_satz=19)
        await _insert(s, "zeiterfassung", mandant_id=m, techniker_id=u, start_at=_ts("2026-01-15T08:00:00"))
        projekt = await _insert(s, "projekte", mandant_id=m, name=f"Projekt {MARKER}", erstellt_von=u)
        await _insert(s, "projekt_aufgaben", mandant_id=m, projekt_id=projekt, titel=f"Aufgabe {MARKER}", erstellt_von=u)
        await _insert(s, "termine", mandant_id=m, vorgang_id=vorgang.id, techniker_id=u, erstellt_von=u, titel=f"Termin {MARKER}",
                      start_at=_ts("2026-02-01T08:00:00"), ende_at=_ts("2026-02-01T10:00:00"))
        await _insert(s, "maengel", mandant_id=m, vorgang_id=vorgang.id, beschreibung=f"Mangel {MARKER}", gemeldet_von=u)
        await _insert(s, "tags", mandant_id=m, label=f"Tag {MARKER}")
        await _insert(s, "boards", mandant_id=m, name=f"Board {MARKER}")
        await _insert(s, "pruefmittel", mandant_id=m, bezeichnung=f"Pruefmittel {MARKER}", kalibrierintervall_monate=12, naechste_kalibrierung_am=heute)
        await _insert(s, "pruefzyklen", mandant_id=m, anlage_id=anlage.id, bezeichnung=f"Zyklus {MARKER}",
                      naechste_pruefung_am=_ts("2026-03-01T00:00:00"), intervall_wert=12)
        await _insert(s, "notifications", mandant_id=m, user_id=u, typ="mention", titel=f"Notiz {MARKER}")
        await _insert(s, "eingangsrechnungen", mandant_id=m, lieferant_name=f"Lief {MARKER}", rechnungsnummer_lieferant=f"E-{MARKER}", rechnungsdatum=heute)
        await _insert(s, "bestellungen", mandant_id=m, bestellnummer=f"B-{MARKER}", erstellt_von=u)
        await _insert(s, "dauerauftraege", mandant_id=m, kunde_id=kunde.id, titel=f"Dauer {MARKER}", abrechnungsart="aufwand",
                      leistungstyp="wartung", intervall_tage=30)
        await _insert(s, "gespeicherte_filter", mandant_id=m, user_id=u, entitaet="vorgaenge", name=f"Filter {MARKER}")
        await _insert(s, "abwesenheitsantraege", mandant_id=m, user_id=u, art="urlaub", von=heute, bis=heute, erstellt_von=u)
        await _insert(s, "form_schemas", mandant_id=m, name=f"Formular {MARKER}")
        await _insert(s, "leistungsverzeichnisse", mandant_id=m, name=f"LV {MARKER}")
        await _insert(s, "nav_kategorien", mandant_id=m, name=f"Nav {MARKER}", reihenfolge=1)
        await _insert(s, "mandant_integrationen", mandant_id=m, typ="smtp", config={"host": MARKER})
        await _insert(s, "einladungen", mandant_id=m, email=f"{MARKER.lower()}@example.de", art="mitarbeiter", rolle="mandant_admin")
        await _insert(s, "org_einheiten", mandant_id=m, name=f"Abteilung {MARKER}", typ="abteilung")
        await _insert(s, "audit_log", mandant_id=m, aktion=f"test.{MARKER}")


async def _id_menge(mandant_id: uuid.UUID) -> set[str]:
    """Alle UUID-Werte aller UUID-Spalten (inkl. FK-Spalten) aller Zeilen eines
    Mandanten, generisch ueber information_schema."""
    async with system_session(grund="test") as s:
        tabellen = (
            await s.execute(
                text(
                    "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                    "AND column_name='mandant_id'"
                )
            )
        ).scalars().all()
        ids: set[str] = {str(mandant_id)}
        for t in tabellen:
            spalten = (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
                        "AND table_name=:t AND data_type='uuid'"
                    ),
                    {"t": t},
                )
            ).scalars().all()
            for c in spalten:
                werte = (
                    await s.execute(
                        text(f'SELECT "{c}" FROM "{t}" WHERE mandant_id = :m AND "{c}" IS NOT NULL'),
                        {"m": mandant_id},
                    )
                ).scalars().all()
                ids.update(str(w) for w in werte)
        return ids


async def _pk_nach_tabelle(mandant_id: uuid.UUID) -> dict[str, list[str]]:
    async with system_session(grund="test") as s:
        tabellen = (
            await s.execute(
                text(
                    "SELECT c.table_name FROM information_schema.columns c "
                    "JOIN information_schema.columns i ON i.table_name=c.table_name AND i.table_schema='public' "
                    "AND i.column_name='id' AND i.data_type='uuid' "
                    "WHERE c.table_schema='public' AND c.column_name='mandant_id'"
                )
            )
        ).scalars().all()
        ergebnis = {}
        for t in tabellen:
            werte = (
                await s.execute(text(f'SELECT id FROM "{t}" WHERE mandant_id = :m LIMIT 3'), {"m": mandant_id})
            ).scalars().all()
            if werte:
                ergebnis[t] = [str(w) for w in werte]
        return ergebnis


def _kandidaten(param: str, pk_b: dict[str, list[str]]) -> list[str]:
    treffer = [i for t, ids in pk_b.items() if _passt(param, t) for i in ids]
    if treffer:
        return treffer
    # Kein Namenstreffer: ein Vertreter je Tabelle, damit unbekannte Parameter
    # trotzdem gegen moeglichst viele Entitaeten geprueft werden.
    return [ids[0] for ids in pk_b.values()]


async def _fremde_ids_ausschliessen(b_ids: set[str], mandant_a) -> set[str]:
    a_ids = await _id_menge(mandant_a.id)
    async with system_session(grund="test") as s:
        global_ids = {
            str(r[0])
            for r in (
                await s.execute(
                    text(
                        "SELECT id FROM account_typen WHERE mandant_id IS NULL "
                        "UNION SELECT id FROM job_laeufe WHERE mandant_id IS NULL"
                    )
                )
            ).all()
        }
    return b_ids - a_ids - global_ids


def _leck_in(body: str, b_ids: set[str]) -> list[str]:
    gefunden = set(_UUID_RE.findall(body.lower())) & b_ids
    if MARKER.lower() in body.lower():
        gefunden.add(MARKER)
    return sorted(gefunden)


@pytest.mark.asyncio
async def test_get_endpunkte_leaken_keine_fremden_mandantendaten(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang, make_vertrag, make_partner
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="disponent", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a, name="Kunde A")
    await make_vorgang(mandant=mandant_a, kunde=kunde_a, titel="Vorgang A")
    kunde_b = await make_kunde(mandant=mandant_b, name=f"Kunde {MARKER}")
    anlage_b = await make_anlage(mandant=mandant_b, kunde=kunde_b, bezeichnung=f"Anlage {MARKER}")
    vorgang_b = await make_vorgang(mandant=mandant_b, kunde=kunde_b, titel=f"Vorgang {MARKER}")
    await make_vertrag(mandant=mandant_b, kunde=kunde_b, bezeichnung=f"Vertrag {MARKER}")
    await make_partner(mandant=mandant_b, name=f"Partner {MARKER}")
    await _b_daten_anlegen(mandant_b, admin_b, kunde_b, vorgang_b, anlage_b)

    b_ids = await _fremde_ids_ausschliessen(await _id_menge(mandant_b.id), mandant_a)
    pk_b = await _pk_nach_tabelle(mandant_b.id)
    # Sanity: der Test hat nur Aussagekraft, wenn B wirklich viele Entitaeten hat.
    assert len(pk_b) >= 35, f"zu wenige B-Tabellen befuellt: {sorted(pk_b)}"
    string_werte = {}
    async with system_session(grund="test") as s:
        for name, (tabelle, spalte) in STRING_PARAMETER.items():
            string_werte[name] = (
                await s.execute(text(f"SELECT {spalte} FROM {tabelle} WHERE mandant_id = :m AND {spalte} IS NOT NULL"), {"m": mandant_b.id})
            ).scalars().first()

    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")
    ha, hb = auth_headers(token_a), auth_headers(token_b)

    leaks: dict[str, str] = {}
    unerwartet: dict[str, str] = {}
    liste_getestet = detail_getestet = 0
    detail_mit_b_treffer = 0  # Positivkontrolle: Detail-Heuristik erreicht als B echte Objekte

    for pfad, params in _get_endpunkte():
        if _ausgenommen(pfad) is not None:
            continue
        if not params:
            resp = await _get(client, pfad, headers=ha)
            liste_getestet += 1
            if resp.status_code in (401,) or resp.status_code >= 500:
                unerwartet[pfad] = f"Status {resp.status_code}"
                continue
            gefunden = _leck_in(resp.content.decode("latin-1"), b_ids)
            if gefunden:
                leaks[pfad] = f"{resp.status_code}: {gefunden[:3]}"
            continue

        # Detail-Endpunkt: je Parameter passende B-IDs einsetzen (Kreuzprodukt, klein).
        kombis: list[dict[str, str]] = [{}]
        ueberspringen = False
        for name, typ in params:
            if typ == "uuid":
                werte = _kandidaten(name, pk_b)
            elif name in string_werte and string_werte[name]:
                werte = [string_werte[name]]
            else:
                unerwartet[pfad] = f"nicht-UUID-Parameter {name!r} ohne Ausnahme/Wertezuordnung"
                ueberspringen = True
                break
            kombis = [{**k, name: w} for k in kombis for w in werte]
        if ueberspringen:
            continue
        # Mehrere Parameter: Kombinationen deckeln, damit die Laufzeit begrenzt bleibt.
        for kombi in kombis[:12]:
            url = pfad
            for name, wert in kombi.items():
                url = url.replace("{" + name + "}", wert)
            resp = await _get(client, url, headers=ha)
            detail_getestet += 1
            if resp.status_code == 401 or resp.status_code >= 500:
                unerwartet[f"{pfad} [{url}]"] = f"Status {resp.status_code}"
                continue
            if resp.status_code == 200:
                gefunden = _leck_in(resp.content.decode("latin-1"), b_ids)
                if gefunden:
                    leaks[pfad] = f"200 auf {url}: {gefunden[:3]}"
        for k in kombis[:12]:
            if (await _get(client, _fuelle(pfad, k), headers=hb)).status_code == 200:
                detail_mit_b_treffer += 1
                break

    echte_leaks = {p: b for p, b in leaks.items() if p not in BEKANNTE_LECKS}
    assert not echte_leaks, "Cross-Tenant-Leaks:\n" + "\n".join(f"  {p}: {b}" for p, b in echte_leaks.items())
    assert not unerwartet, "Unerwartete Antworten:\n" + "\n".join(f"  {p}: {b}" for p, b in unerwartet.items())
    assert liste_getestet >= 60 and detail_getestet >= 100, (liste_getestet, detail_getestet)
    assert detail_mit_b_treffer >= 40, f"Positivkontrolle schwach: {detail_mit_b_treffer}"
    if leaks:
        pytest.xfail("bekannte Leaks: " + ", ".join(leaks))


async def _get(client, url: str, headers: dict):
    """Serverfehler (die ASGITransport als Exception durchreicht) als 500 werten,
    statt den ganzen Lauf abzubrechen."""
    try:
        return await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return httpx.Response(500, text=f"{type(exc).__name__}: {exc}")


def _fuelle(pfad: str, kombi: dict[str, str]) -> str:
    for name, wert in kombi.items():
        pfad = pfad.replace("{" + name + "}", wert)
    return pfad
