from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.schemas.telefonat import (
    KontaktverlaufEintrag,
    TelefonatAnzahlRueckrufe,
    TelefonatCreate,
    TelefonatRead,
    TelefonatUpdate,
)
from app.services import telefonat_service

# Rechte (vorgaenge.sehen bzw. kunden.sehen) haengen vom Bezug des einzelnen Telefonats ab und werden deshalb im
# Service geprueft, nicht als Router-Abhaengigkeit.
router = APIRouter(
    prefix="/api/telefonate",
    tags=["telefonate"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)

# Kontaktverlauf am Kunden: gleiche Rollen wie die Kunden-Routen.
kontaktverlauf_router = APIRouter(
    prefix="/api/kunden/{kunde_id}",
    tags=["telefonate"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "sehen")),
    ],
)


@router.post("", response_model=TelefonatRead, status_code=status.HTTP_201_CREATED)
async def telefonat_anlegen(
    body: TelefonatCreate,
    response: Response,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TelefonatRead:
    telefonat, neu = await telefonat_service.anlegen(session, auth, body)
    if not neu:
        response.status_code = status.HTTP_200_OK
    return telefonat


@router.get("", response_model=list[TelefonatRead])
async def telefonate_auflisten(
    kunde_id: UUID | None = None,
    vorgang_id: UUID | None = None,
    rueckruf_offen: bool = False,
    von_mir: bool = False,
    ergebnis: str | None = Query(default=None, pattern="^(erreicht|nicht_erreicht|mailbox)$"),
    seite: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[TelefonatRead]:
    return await telefonat_service.liste(
        session, auth, kunde_id=kunde_id, vorgang_id=vorgang_id, rueckruf_offen=rueckruf_offen,
        von_mir=von_mir, ergebnis=ergebnis, seite=seite, limit=limit,
    )


@router.get("/anzahl-offene-rueckrufe", response_model=TelefonatAnzahlRueckrufe)
async def anzahl_offene_rueckrufe(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TelefonatAnzahlRueckrufe:
    return TelefonatAnzahlRueckrufe(anzahl=await telefonat_service.anzahl_offene_rueckrufe(session, auth))


@router.get("/{telefonat_id}", response_model=TelefonatRead)
async def telefonat_lesen(
    telefonat_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TelefonatRead:
    return await telefonat_service.lesemodell(session, auth, telefonat_id)


@router.patch("/{telefonat_id}", response_model=TelefonatRead)
async def telefonat_aendern(
    telefonat_id: UUID,
    body: TelefonatUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TelefonatRead:
    return await telefonat_service.aktualisieren(session, auth, telefonat_id, body)


@router.delete("/{telefonat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def telefonat_loeschen(
    telefonat_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await telefonat_service.loeschen(session, auth, telefonat_id)


@kontaktverlauf_router.get("/kontaktverlauf", response_model=list[KontaktverlaufEintrag])
async def kontaktverlauf(
    kunde_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[KontaktverlaufEintrag]:
    return await telefonat_service.kontaktverlauf(session, auth, kunde_id, limit)
