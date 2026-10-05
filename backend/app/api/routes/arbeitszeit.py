from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.zeit import tagesbeginn_utc, tagesende_utc
from app.models.arbeitszeit import ArbeitszeitSoll, Feiertag
from app.models.mandant import Mandant
from app.models.user import User
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.arbeitszeit import (
    ArbeitszeitSollRead,
    ArbeitszeitSollSetzen,
    BundeslandRead,
    BundeslandUpdate,
    FeiertageGenerieren,
    FeiertageGenerierenErgebnis,
    FeiertagCreate,
    FeiertagRead,
    SaldoRead,
)
from app.services import arbeitszeit_service
from app.services.rechte_service import darf_abwesenheiten_verwalten

router = APIRouter(
    prefix="/api/arbeitszeit",
    tags=["arbeitszeit"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)


async def _verwalten_pruefen(auth: AuthContext, session: AsyncSession) -> None:
    if not await darf_abwesenheiten_verwalten(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung zum Verwalten von Arbeitszeit und Feiertagen",
        )


async def _ziel_user(
    user_id: UUID | None, auth: AuthContext, session: AsyncSession, *, schreiben: bool = False
) -> UUID:
    """Eigener Nutzer ist immer lesbar; fremder Zugriff und jedes Schreiben
    brauchen das Recht. Fremde Mandanten sind per RLS unsichtbar und liefern
    404 statt 403, damit die Existenz einer ID nicht verraten wird."""
    ziel_id = user_id or auth.user_id
    if schreiben or ziel_id != auth.user_id:
        await _verwalten_pruefen(auth, session)
    if ziel_id != auth.user_id:
        user = await session.get(User, ziel_id)
        if user is None or user.mandant_id != auth.mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden")
    return ziel_id


@router.get("/soll", response_model=list[ArbeitszeitSollRead])
async def list_soll(
    user_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ArbeitszeitSoll]:
    ziel_id = await _ziel_user(user_id, auth, session)
    result = await session.execute(
        select(ArbeitszeitSoll)
        .where(ArbeitszeitSoll.user_id == ziel_id)
        .order_by(ArbeitszeitSoll.gueltig_ab.desc())
    )
    return list(result.scalars().all())


@router.put("/soll/{user_id}", response_model=ArbeitszeitSollRead)
async def soll_setzen(
    user_id: UUID,
    body: ArbeitszeitSollSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ArbeitszeitSoll:
    ziel_id = await _ziel_user(user_id, auth, session, schreiben=True)
    result = await session.execute(
        select(ArbeitszeitSoll).where(
            ArbeitszeitSoll.user_id == ziel_id, ArbeitszeitSoll.gueltig_ab == body.gueltig_ab
        )
    )
    zeile = result.scalar_one_or_none()
    werte = body.model_dump()
    if zeile is None:
        zeile = ArbeitszeitSoll(mandant_id=auth.mandant_id, user_id=ziel_id, **werte)
        session.add(zeile)
    else:
        for feld, wert in werte.items():
            setattr(zeile, feld, wert)
    await session.flush()
    await session.refresh(zeile)
    return zeile


@router.get("/feiertage", response_model=list[FeiertagRead])
async def list_feiertage(
    jahr: int = Query(ge=2000, le=2100),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Feiertag]:
    result = await session.execute(
        select(Feiertag)
        .where(Feiertag.datum >= date(jahr, 1, 1), Feiertag.datum <= date(jahr, 12, 31))
        .order_by(Feiertag.datum)
    )
    return list(result.scalars().all())


@router.post("/feiertage", response_model=FeiertagRead, status_code=status.HTTP_201_CREATED)
async def feiertag_anlegen(
    body: FeiertagCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Feiertag:
    await _verwalten_pruefen(auth, session)
    feiertag = Feiertag(mandant_id=auth.mandant_id, datum=body.datum, bezeichnung=body.bezeichnung.strip())
    session.add(feiertag)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Für dieses Datum existiert bereits ein Feiertag"
        ) from exc
    return feiertag


@router.post("/feiertage/generieren", response_model=FeiertageGenerierenErgebnis)
async def feiertage_generieren(
    body: FeiertageGenerieren,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FeiertageGenerierenErgebnis:
    await _verwalten_pruefen(auth, session)
    mandant = await session.get(Mandant, auth.mandant_id)
    vorhanden = set(
        (
            await session.execute(
                select(Feiertag.datum).where(
                    Feiertag.datum >= date(body.jahr, 1, 1), Feiertag.datum <= date(body.jahr, 12, 31)
                )
            )
        )
        .scalars()
        .all()
    )
    angelegt = 0
    uebersprungen = 0
    for datum, bezeichnung in arbeitszeit_service.feiertage_fuer(mandant.bundesland, body.jahr):
        # Vorhandene (auch umbenannte oder manuell angelegte) Tage bleiben
        # unangetastet, damit Nachbearbeitungen einen erneuten Lauf ueberleben.
        if datum in vorhanden:
            uebersprungen += 1
            continue
        session.add(Feiertag(mandant_id=auth.mandant_id, datum=datum, bezeichnung=bezeichnung))
        angelegt += 1
    await session.flush()
    gesamt = await list_feiertage(body.jahr, auth, session)
    return FeiertageGenerierenErgebnis(angelegt=angelegt, uebersprungen=uebersprungen, feiertage=gesamt)


@router.delete("/feiertage/{feiertag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def feiertag_loeschen(
    feiertag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await _verwalten_pruefen(auth, session)
    feiertag = await session.get(Feiertag, feiertag_id)
    if feiertag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feiertag nicht gefunden")
    await session.delete(feiertag)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/bundesland", response_model=BundeslandRead)
async def get_bundesland(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> BundeslandRead:
    mandant = await session.get(Mandant, auth.mandant_id)
    return BundeslandRead(bundesland=mandant.bundesland)


@router.patch("/bundesland", response_model=BundeslandRead)
async def bundesland_setzen(
    body: BundeslandUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BundeslandRead:
    await _verwalten_pruefen(auth, session)
    mandant = await session.get(Mandant, auth.mandant_id)
    mandant.bundesland = body.bundesland
    await session.flush()
    return BundeslandRead(bundesland=mandant.bundesland)


@router.get("/saldo", response_model=SaldoRead)
async def get_saldo(
    von: date,
    bis: date,
    user_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SaldoRead:
    if bis < von:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="'bis' liegt vor 'von'")
    if (bis - von).days + 1 > arbeitszeit_service.SALDO_MAX_TAGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Zeitraum darf höchstens {arbeitszeit_service.SALDO_MAX_TAGE} Tage umfassen",
        )
    ziel_id = await _ziel_user(user_id, auth, session)

    soll_zeilen = list(
        (await session.execute(select(ArbeitszeitSoll).where(ArbeitszeitSoll.user_id == ziel_id)))
        .scalars()
        .all()
    )
    feiertage = set(
        (await session.execute(select(Feiertag.datum).where(Feiertag.datum >= von, Feiertag.datum <= bis)))
        .scalars()
        .all()
    )
    zeilen = (
        await session.execute(
            select(Zeiterfassung.start_at, Zeiterfassung.ende_at, Zeiterfassung.kategorie).where(
                Zeiterfassung.techniker_id == ziel_id,
                Zeiterfassung.geloescht_am.is_(None),
                Zeiterfassung.start_at >= tagesbeginn_utc(von),
                Zeiterfassung.start_at < tagesende_utc(bis),
            )
        )
    ).all()
    ergebnis = arbeitszeit_service.berechne_saldo(
        von,
        bis,
        soll_zeilen,
        feiertage,
        [arbeitszeit_service.ZeitEintrag(z.start_at, z.ende_at, z.kategorie) for z in zeilen],
        datetime.now(timezone.utc),
    )
    return SaldoRead(
        soll_stunden=ergebnis.soll_stunden,
        ist_stunden=ergebnis.ist_stunden,
        saldo_stunden=ergebnis.saldo_stunden,
        tage=[
            {
                "datum": t.datum,
                "soll": t.soll,
                "ist": t.ist,
                "saldo": t.saldo,
                "feiertag": t.feiertag,
                "abwesenheit": t.abwesenheit,
            }
            for t in ergebnis.tage
        ],
    )
