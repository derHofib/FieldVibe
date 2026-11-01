"""Mandanten-Exporte (Vollexport, Z3): nur mandant_admin, asynchron, 7 Tage abrufbar."""
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, nur_mandant_admin
from app.models.mandant_export import MandantExport
from app.services import audit_service, export_job_service

router = APIRouter(prefix="/api/exporte", tags=["exporte"], dependencies=[Depends(nur_mandant_admin)])

# Z3 ueber mehr als diese Spanne waere mehr als ein Prueffenster (ueblich: 1-3 Jahre).
_Z3_MAX_TAGE = 366 * 5


class ExportRead(BaseModel):
    id: UUID
    art: str
    status: str
    parameter: dict
    angefordert_von: UUID
    angefordert_am: datetime
    fertig_am: datetime | None
    laeuft_ab_am: datetime | None
    groesse_bytes: int | None
    sha256: str | None
    anzahl_dateien: int | None
    fehler: str | None

    model_config = {"from_attributes": True}


class Z3Anforderung(BaseModel):
    von: date
    bis: date

    @model_validator(mode="after")
    def _zeitraum(self):
        if self.bis < self.von:
            raise ValueError("'bis' darf nicht vor 'von' liegen")
        if (self.bis - self.von).days > _Z3_MAX_TAGE:
            raise ValueError("Der Zeitraum darf höchstens fünf Jahre umfassen")
        return self


class DownloadUrl(BaseModel):
    url: str
    gueltig_bis: datetime
    sha256: str | None


async def _anfordern(session: AsyncSession, auth: AuthContext, art: str, parameter: dict) -> MandantExport:
    try:
        return await export_job_service.anfordern(
            session, mandant_id=auth.mandant_id, user_id=auth.user_id, art=art, parameter=parameter
        )
    except export_job_service.ExportLaeuftBereits as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es läuft bereits ein Export für Ihren Betrieb – bitte warten, bis er fertig ist.",
        ) from exc


@router.post("/vollexport", response_model=ExportRead, status_code=status.HTTP_202_ACCEPTED)
async def vollexport_anfordern(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> MandantExport:
    return await _anfordern(session, auth, "vollexport", {})


@router.post("/z3", response_model=ExportRead, status_code=status.HTTP_202_ACCEPTED)
async def z3_anfordern(
    body: Z3Anforderung, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> MandantExport:
    return await _anfordern(session, auth, "z3", {"von": body.von, "bis": body.bis})


@router.get("", response_model=list[ExportRead])
async def list_exporte(session: AsyncSession = Depends(get_db)) -> list[MandantExport]:
    result = await session.execute(select(MandantExport).order_by(MandantExport.angefordert_am.desc()).limit(20))
    return list(result.scalars().all())


async def _laden(session: AsyncSession, export_id: UUID) -> MandantExport:
    job = await session.get(MandantExport, export_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export nicht gefunden")
    return job


@router.get("/{export_id}", response_model=ExportRead)
async def get_export(export_id: UUID, session: AsyncSession = Depends(get_db)) -> MandantExport:
    return await _laden(session, export_id)


@router.get("/{export_id}/download-url", response_model=DownloadUrl)
async def get_download_url(
    export_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> DownloadUrl:
    job = await _laden(session, export_id)
    if job.status != "fertig" or not job.object_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der Export ist abgelaufen" if job.status == "abgelaufen" else "Der Export ist noch nicht fertig",
        )
    url, gueltig_bis = export_job_service.download_url(job)
    await audit_service.export_protokollieren(
        session,
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        art=f"{job.art}_download",
        export_id=str(job.id),
    )
    return DownloadUrl(url=url, gueltig_bis=gueltig_bis, sha256=job.sha256)
