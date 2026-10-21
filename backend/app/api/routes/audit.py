"""Einsicht ins Mandanten-Protokoll (nur mandant_admin). Das plattformweite Protokoll
fuer den Super-Admin bleibt unter /api/admin/audit-log."""
import json
from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.audit_log import AKTEUR_TYPEN, AuditLog
from app.models.user import User
from app.schemas.audit import AuditEintragRead, AuditKettenFehler, AuditListe, AuditVerifikation
from app.services import audit_service
from app.services.csv_service import csv_response, formel_sicher

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)

_CSV_MAX_ZEILEN = 50000


def _filter(
    stmt: Select,
    *,
    mandant_id: UUID,
    von: date | None,
    bis: date | None,
    aktion: str | None,
    entity_type: str | None,
    entity_id: UUID | None,
    actor_user_id: UUID | None,
    akteur_typ: str | None,
) -> Select:
    stmt = stmt.where(AuditLog.mandant_id == mandant_id)
    if von is not None:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(von, time.min, tzinfo=timezone.utc))
    if bis is not None:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(bis, time.max, tzinfo=timezone.utc))
    if aktion:
        # Exakt oder Praefix ("rechnung_" findet alle Rechnungsereignisse); % und _ sind
        # beim Praefix literal gemeint.
        muster = aktion.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(AuditLog.aktion.like(f"{muster}%", escape="\\"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if akteur_typ:
        stmt = stmt.where(AuditLog.akteur_typ == akteur_typ)
    return stmt


def _zeile_zu_read(eintrag: AuditLog, name: str | None) -> AuditEintragRead:
    return AuditEintragRead(
        id=eintrag.id,
        zeit=eintrag.created_at,
        akteur_typ=eintrag.akteur_typ,
        actor_user_id=eintrag.actor_user_id,
        actor_name=name,
        aktion=eintrag.aktion,
        entity_type=eintrag.entity_type,
        entity_id=eintrag.entity_id,
        payload=eintrag.payload,
        request_id=eintrag.request_id,
        ip=eintrag.ip,
    )


@router.get("", response_model=AuditListe)
async def list_audit(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    aktion: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    akteur_typ: str | None = Query(default=None, pattern=f"^({'|'.join(AKTEUR_TYPEN)})$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditListe:
    filt = dict(
        mandant_id=auth.mandant_id,
        von=von,
        bis=bis,
        aktion=aktion,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        akteur_typ=akteur_typ,
    )
    gesamt = await session.scalar(_filter(select(func.count()).select_from(AuditLog), **filt))
    zeilen = (
        await session.execute(
            _filter(select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.actor_user_id), **filt)
            .order_by(AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return AuditListe(eintraege=[_zeile_zu_read(e, n) for e, n in zeilen], gesamt=gesamt or 0)


@router.get("/export.csv")
async def export_audit_csv(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    von: date | None = None,
    bis: date | None = None,
    aktion: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    akteur_typ: str | None = Query(default=None, pattern=f"^({'|'.join(AKTEUR_TYPEN)})$"),
):
    zeilen = (
        await session.execute(
            _filter(
                select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.actor_user_id),
                mandant_id=auth.mandant_id,
                von=von,
                bis=bis,
                aktion=aktion,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_user_id=actor_user_id,
                akteur_typ=akteur_typ,
            )
            .order_by(AuditLog.id)
            .limit(_CSV_MAX_ZEILEN)
        )
    ).all()
    kopf = ["ID", "Zeit (UTC)", "Akteur-Typ", "Akteur", "Aktion", "Objekttyp", "Objekt-ID", "Details", "Request-ID", "IP (gekürzt)"]
    daten = [
        [
            e.id,
            e.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            e.akteur_typ,
            formel_sicher(name or ""),
            e.aktion,
            e.entity_type or "",
            str(e.entity_id) if e.entity_id else "",
            formel_sicher(json.dumps(e.payload, ensure_ascii=False, sort_keys=True)),
            e.request_id or "",
            e.ip or "",
        ]
        for e, name in zeilen
    ]
    await audit_service.log_action(
        session,
        aktion="export_audit_csv",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="export",
        payload={"zeilen": len(daten), "von": von, "bis": bis, "aktion": aktion},
    )
    return csv_response(kopf, daten, "protokoll.csv")


@router.get("/aktionen", response_model=list[str])
async def list_aktionen(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[str]:
    result = await session.execute(
        select(AuditLog.aktion).where(AuditLog.mandant_id == auth.mandant_id).distinct().order_by(AuditLog.aktion)
    )
    return list(result.scalars().all())


@router.get("/verifizieren", response_model=AuditVerifikation)
async def verifizieren(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> AuditVerifikation:
    ergebnis = await audit_service.kette_pruefen(session, auth.mandant_id)
    return AuditVerifikation(
        ok=ergebnis.ok,
        geprueft=ergebnis.geprueft,
        kopf_seq=ergebnis.kopf_seq,
        kopf_hash=ergebnis.kopf_hash,
        ohne_siegel=ergebnis.ohne_siegel,
        legacy_eintraege=ergebnis.legacy_eintraege,
        fehler=[AuditKettenFehler(seq=f.seq, audit_log_id=f.audit_log_id, grund=f.grund) for f in ergebnis.fehler],
    )
