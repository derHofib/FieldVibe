"""Audit-Protokoll (append-only, je Mandant hash-verkettet).

Schreibpfad: log_action() legt den Eintrag in derselben Transaktion an wie die
Fachaenderung. Scheitert das Protokollieren (oder das Siegeln kurz vor dem
COMMIT), scheitert die ganze Transaktion -- bewusst: GoBD verlangt, dass es
keine Belegaenderung ohne Protokoll gibt; ein "Fachlogik geht durch, Protokoll
fehlt" waere der schlimmere Fehler. Ausnahme sind Pfade, die ihre eigene
Transaktion fuer einen Fehlschlag brauchen (Login-Fehler, siehe
login_fehlschlag_protokollieren).

Siegel: die Kette (audit_log_siegel) wird erst im before_commit-Hook der Session
gebildet. Der Advisory-Lock je Mandant haelt damit nur noch Siegel-INSERT und
COMMIT; wuerde er schon beim INSERT des Eintrags genommen, koennten zwei
Transaktionen, die danach noch Fachzeilen sperren, sich gegenseitig
verklemmen.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from contextvars import ContextVar
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import event, func, insert, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.audit_log import AKTEUR_TYPEN, AuditLog, AuditLogSiegel

SIEGEL_GENESIS = "0" * 64
_PENDING_KEY = "audit_siegel_vorgemerkt"

# Aktionen, bei denen die (gekuerzte) IP mitgeschrieben wird: Anmeldung und
# Konto-Sicherheit. Fuer Belegvorgaenge ist sie ohne Mehrwert und nur Datenhaltung.
AKTIONEN_MIT_IP = frozenset(
    {
        "login",
        "login_fehlgeschlagen",
        "logout",
        "logout_alle_geraete",
        "passwort_geaendert",
        "passwort_zurueckgesetzt",
        "mfa_aktiviert",
        "mfa_deaktiviert",
        "mfa_zurueckgesetzt",
        "mfa_wiederherstellungscodes_erneuert",
        "mfa_wiederherstellungscode_verwendet",
        "login_als_mandant",
    }
)

# Schluessel, deren Werte nie ins Protokoll gehoeren (Tokens, Geheimnisse, Hashes).
_GEHEIM = re.compile(r"passwor|token|secret|api[_-]?key|authorization|credential|totp|recovery|wiederherstellungscode$|hash$", re.I)

_request_id: ContextVar[str | None] = ContextVar("audit_request_id", default=None)
_client_ip: ContextVar[str | None] = ContextVar("audit_client_ip", default=None)


def kontext_setzen(request_id: str | None, ip: str | None):
    return _request_id.set(request_id), _client_ip.set(ip)


def kontext_zuruecksetzen(tokens) -> None:
    _request_id.reset(tokens[0])
    _client_ip.reset(tokens[1])


def ip_kuerzen(ip: str | None) -> str | None:
    """Datensparsam: IPv4 auf /24, IPv6 auf /48. Reicht zur Einordnung (Netz/Standort),
    identifiziert aber keinen einzelnen Anschluss mehr."""
    if not ip:
        return None
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if isinstance(adresse, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{adresse}/24", strict=False).network_address)
    if adresse.ipv4_mapped is not None:
        return str(ipaddress.ip_network(f"{adresse.ipv4_mapped}/24", strict=False).network_address)
    return str(ipaddress.ip_network(f"{adresse}/48", strict=False).network_address) + "/48"


def bereinigen(wert):
    """Maskiert rekursiv Werte von Schluesseln, die nach Geheimnis aussehen. Defensiv: die
    Aufrufer sollen ohnehin nichts Derartiges uebergeben."""
    if isinstance(wert, dict):
        return {k: ("***" if _GEHEIM.search(str(k)) else bereinigen(v)) for k, v in wert.items()}
    if isinstance(wert, list):
        return [bereinigen(v) for v in wert]
    return wert


async def log_action(
    session: AsyncSession,
    *,
    aktion: str,
    mandant_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    payload: dict | None = None,
    akteur_typ: str | None = None,
) -> AuditLog:
    if akteur_typ is None:
        akteur_typ = "user" if actor_user_id is not None else "system"
    if akteur_typ not in AKTEUR_TYPEN:
        raise ValueError(f"Unbekannter Akteurtyp: {akteur_typ}")
    entry = AuditLog(
        aktion=aktion,
        mandant_id=mandant_id,
        actor_user_id=actor_user_id,
        akteur_typ=akteur_typ,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=bereinigen(jsonable_encoder(payload or {})),
        request_id=_request_id.get(),
        ip=ip_kuerzen(_client_ip.get()) if aktion in AKTIONEN_MIT_IP else None,
    )
    session.add(entry)
    await session.flush()
    if mandant_id is not None:
        session.sync_session.info.setdefault(_PENDING_KEY, []).append(entry)
    return entry


async def log_aenderung(
    session: AsyncSession,
    *,
    aktion: str,
    mandant_id: UUID | None,
    actor_user_id: UUID | None,
    entity_type: str,
    entity_id: UUID | None,
    vorher: dict | None,
    nachher: dict | None,
) -> AuditLog:
    """Strukturierter Vorher/Nachher-Eintrag (Organigramm, Rechte, Account-Typen).
    jsonable_encoder, weil UUID/datetime im Payload nicht JSON-serialisierbar sind."""
    return await log_action(
        session,
        aktion=aktion,
        mandant_id=mandant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=jsonable_encoder({"vorher": vorher, "nachher": nachher}),
    )


async def export_protokollieren(
    session: AsyncSession, *, mandant_id: UUID, actor_user_id: UUID, art: str, **parameter
) -> AuditLog:
    """Datenabfluss (DATEV, UStVA, CSV, Z3, Vollexport): nur Art und Parameter
    (Zeitraum, Filter, Zeilenzahl), nie der Inhalt."""
    return await log_action(
        session,
        aktion=f"export_{art}",
        mandant_id=mandant_id,
        actor_user_id=actor_user_id,
        entity_type="export",
        payload={k: v for k, v in parameter.items() if v is not None},
    )


# --- Siegel (Hash-Kette) ---------------------------------------------------


def inhalt_fuer_hash(e: AuditLog) -> str:
    """Kanonische Serialisierung eines gespeicherten Eintrags. Wird sowohl beim
    Siegeln als auch beim Pruefen aus den aus der DB gelesenen Werten gebildet,
    damit JSON-Rundlauf (JSONB) und Zeitzonen keine Scheinabweichung erzeugen."""
    zeit = e.created_at
    if zeit.tzinfo is None:
        zeit = zeit.replace(tzinfo=timezone.utc)
    return json.dumps(
        {
            "id": e.id,
            "mandant_id": str(e.mandant_id),
            "zeit": zeit.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "akteur_typ": e.akteur_typ,
            "aktion": e.aktion,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "payload": e.payload,
            "request_id": e.request_id,
            "ip": e.ip,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def siegel_hash(vorgaenger_hash: str, e: AuditLog) -> str:
    return hashlib.sha256(f"{vorgaenger_hash}|{inhalt_fuer_hash(e)}".encode("utf-8")).hexdigest()


def _siegeln(session: Session) -> None:
    vorgemerkt: list[AuditLog] | None = session.info.pop(_PENDING_KEY, None)
    if not vorgemerkt:
        return
    # In einem zurueckgerollten Savepoint angelegte Eintraege sind nicht mehr persistent.
    ids = [e.id for e in vorgemerkt if e in session and sa_inspect(e).persistent]
    if not ids:
        return
    zeilen = (
        session.execute(
            select(AuditLog).where(AuditLog.id.in_(ids)).order_by(AuditLog.id).execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )
    je_mandant: dict[UUID, list[AuditLog]] = {}
    for z in zeilen:
        je_mandant.setdefault(z.mandant_id, []).append(z)
    # Feste Reihenfolge der Locks, falls eine Transaktion mehrere Mandanten beruehrt.
    for mandant_id in sorted(je_mandant, key=str):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"audit-siegel:{mandant_id}"}
        )
        letzter = session.execute(
            select(AuditLogSiegel.seq, AuditLogSiegel.hash)
            .where(AuditLogSiegel.mandant_id == mandant_id)
            .order_by(AuditLogSiegel.seq.desc())
            .limit(1)
        ).first()
        seq, vorher = (letzter.seq, letzter.hash) if letzter else (0, SIEGEL_GENESIS)
        neue = []
        for z in je_mandant[mandant_id]:
            seq += 1
            h = siegel_hash(vorher, z)
            neue.append(
                {"mandant_id": mandant_id, "seq": seq, "audit_log_id": z.id, "vorgaenger_hash": vorher, "hash": h}
            )
            vorher = h
        session.execute(insert(AuditLogSiegel), neue)


async def siegel_vor_antwort(request: Request) -> AsyncIterator[None]:
    """Globale Abhaengigkeit mit scope="function" (siehe main.py): Der COMMIT der
    Request-Session passiert erst beim Abbau von get_db, also nachdem die Antwort
    schon unterwegs ist -- ein scheiternder Siegel-INSERT wuerde sonst als 2xx
    quittiert, obwohl die Fachaenderung zurueckgerollt wird. Hier wird deshalb
    vor dem Senden gesiegelt; ein Fehler wird zum 500 und rollt alles zurueck."""
    yield
    session = getattr(request.state, "audit_session", None)
    if session is not None:
        await session.run_sync(_siegeln)


@event.listens_for(Session, "before_commit")
def _vor_commit(session: Session) -> None:
    _siegeln(session)


@event.listens_for(Session, "after_soft_rollback")
def _nach_rollback(session: Session, previous_transaction) -> None:
    # Nur beim Rollback der aeussersten Transaktion verwerfen; ein zurueckgerollter
    # Savepoint wird in _siegeln ueber die Persistenz der Eintraege herausgefiltert.
    if previous_transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)


# --- Pruefung ----------------------------------------------------------------


@dataclass
class KettenFehler:
    seq: int | None
    audit_log_id: int | None
    grund: str


@dataclass
class KettenPruefung:
    ok: bool
    geprueft: int
    kopf_seq: int | None
    kopf_hash: str | None
    ohne_siegel: int
    legacy_eintraege: int
    fehler: list[KettenFehler] = field(default_factory=list)


_MAX_FEHLER = 20
_SEITE = 2000


async def kette_pruefen(session: AsyncSession, mandant_id: UUID) -> KettenPruefung:
    """Rechnet die Kette des Mandanten neu: lueckenlose seq, Verweis auf den
    Vorgaengerhash, Hash ueber den heute gespeicherten Eintrag. Abgeschnittene
    Kettenenden erkennt das allein nicht -- dafuer liefert das Ergebnis den
    Kopf (kopf_seq/kopf_hash), den ein Betrieb extern festhalten kann."""
    fehler: list[KettenFehler] = []
    erwartet_seq = 1
    vorher = SIEGEL_GENESIS
    geprueft = 0
    kopf_seq = None
    kopf_hash = None
    nach_seq = 0
    while True:
        zeilen = (
            await session.execute(
                select(AuditLogSiegel, AuditLog)
                .join(AuditLog, AuditLog.id == AuditLogSiegel.audit_log_id)
                .where(AuditLogSiegel.mandant_id == mandant_id, AuditLogSiegel.seq > nach_seq)
                .order_by(AuditLogSiegel.seq)
                .limit(_SEITE)
            )
        ).all()
        if not zeilen:
            break
        for siegel, eintrag in zeilen:
            geprueft += 1
            if siegel.seq != erwartet_seq and len(fehler) < _MAX_FEHLER:
                fehler.append(KettenFehler(siegel.seq, eintrag.id, f"Lücke in der Kette (erwartet {erwartet_seq})"))
            if siegel.vorgaenger_hash != vorher and len(fehler) < _MAX_FEHLER:
                fehler.append(KettenFehler(siegel.seq, eintrag.id, "Vorgängerhash passt nicht zur Kette"))
            if siegel.hash != siegel_hash(siegel.vorgaenger_hash, eintrag) and len(fehler) < _MAX_FEHLER:
                fehler.append(KettenFehler(siegel.seq, eintrag.id, "Inhalt des Eintrags stimmt nicht mit dem Siegel überein"))
            erwartet_seq = siegel.seq + 1
            vorher = siegel.hash
            kopf_seq, kopf_hash = siegel.seq, siegel.hash
            nach_seq = siegel.seq

    ohne = await session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .outerjoin(AuditLogSiegel, AuditLogSiegel.audit_log_id == AuditLog.id)
        .where(AuditLog.mandant_id == mandant_id, AuditLog.legacy.is_(False), AuditLogSiegel.id.is_(None))
    )
    legacy = await session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.mandant_id == mandant_id, AuditLog.legacy.is_(True))
    )
    if ohne:
        fehler.append(KettenFehler(None, None, f"{ohne} Eintrag/Einträge ohne Siegel"))
    return KettenPruefung(
        ok=not fehler,
        geprueft=geprueft,
        kopf_seq=kopf_seq,
        kopf_hash=kopf_hash,
        ohne_siegel=ohne or 0,
        legacy_eintraege=legacy or 0,
        fehler=fehler,
    )


async def login_fehlschlag_protokollieren(
    *, mandant_id: UUID | None, user_id: UUID, grund: str
) -> None:
    """Eigene Transaktion: der Login-Pfad bricht danach mit 401 ab, dessen
    Rollback wuerde einen Eintrag in der Aufrufer-Session mitnehmen."""
    from app.db.session import system_session

    if mandant_id is None:
        return
    async with system_session() as session:
        await log_action(
            session,
            aktion="login_fehlgeschlagen",
            mandant_id=mandant_id,
            actor_user_id=user_id,
            entity_type="user",
            entity_id=user_id,
            payload={"grund": grund},
        )
