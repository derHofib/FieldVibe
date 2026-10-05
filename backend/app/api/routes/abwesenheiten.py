from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.zeit import in_lokal
from app.models.abwesenheit import Abwesenheitsantrag, Urlaubsanspruch
from app.models.user import User
from app.schemas.abwesenheit import (
    AbwesenheitAblehnen,
    AbwesenheitCreate,
    AbwesenheitRead,
    AbwesenheitStatus,
    KalenderEintragRead,
    UrlaubsanspruchRead,
    UrlaubsanspruchSetzen,
    UrlaubskontoRead,
)
from app.services import abwesenheit_service as svc
from app.services.rechte_service import darf_abwesenheiten_verwalten

router = APIRouter(
    prefix="/api/abwesenheiten",
    tags=["abwesenheiten"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)


async def _darf_verwalten(auth: AuthContext, session: AsyncSession) -> bool:
    return await darf_abwesenheiten_verwalten(session, role=auth.role, account_typ_id=auth.account_typ_id)


async def _verwalten_pruefen(auth: AuthContext, session: AsyncSession, detail: str) -> None:
    if not await _darf_verwalten(auth, session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def _user_pruefen(user_id: UUID, auth: AuthContext, session: AsyncSession) -> User:
    """Fremde Mandanten sind per RLS unsichtbar; der explizite Vergleich
    deckt zusaetzlich den Super-Admin-Fall ab. 404 statt 403, damit die
    Existenz einer ID nicht verraten wird."""
    user = await session.get(User, user_id)
    if user is None or user.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nutzer nicht gefunden")
    return user


async def _ziel_user(user_id: UUID | None, auth: AuthContext, session: AsyncSession, detail: str) -> UUID:
    ziel_id = user_id or auth.user_id
    if ziel_id != auth.user_id:
        await _verwalten_pruefen(auth, session, detail)
        await _user_pruefen(ziel_id, auth, session)
    return ziel_id


async def _antrag_laden(antrag_id: UUID, session: AsyncSession) -> Abwesenheitsantrag:
    antrag = await session.get(Abwesenheitsantrag, antrag_id)
    if antrag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abwesenheitsantrag nicht gefunden")
    return antrag


async def _antraege_lesen(session: AsyncSession, antraege: list[Abwesenheitsantrag]) -> list[AbwesenheitRead]:
    tage = await svc.tage_je_antrag(session, antraege)
    namen = await _namen(session, {a.user_id for a in antraege})
    return [
        AbwesenheitRead(
            id=a.id,
            user_id=a.user_id,
            user_name=namen.get(a.user_id, ""),
            art=a.art,
            von=a.von,
            bis=a.bis,
            halber_tag_von=a.halber_tag_von,
            halber_tag_bis=a.halber_tag_bis,
            tage=svc.summe_tage(tage[a.id]),
            status=a.status,
            notiz=a.notiz,
            antwort=a.antwort,
            erstellt_von=a.erstellt_von,
            erstellt_am=a.erstellt_am,
            bearbeitet_von=a.bearbeitet_von,
            bearbeitet_am=a.bearbeitet_am,
        )
        for a in antraege
    ]


async def _namen(session: AsyncSession, user_ids: set[UUID]) -> dict[UUID, str]:
    if not user_ids:
        return {}
    rows = (await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all()
    return {uid: name for uid, name in rows}


async def _lesen(session: AsyncSession, antrag: Abwesenheitsantrag) -> AbwesenheitRead:
    await session.refresh(antrag)
    return (await _antraege_lesen(session, [antrag]))[0]


@router.post("", response_model=AbwesenheitRead, status_code=status.HTTP_201_CREATED)
async def antrag_stellen(
    body: AbwesenheitCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AbwesenheitRead:
    ziel_id = await _ziel_user(
        body.user_id, auth, session, "Abwesenheiten für andere Mitarbeiter einzutragen erfordert eine Berechtigung"
    )
    if (body.bis - body.von).days + 1 > svc.ANTRAG_MAX_TAGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Ein Antrag darf höchstens {svc.ANTRAG_MAX_TAGE} Tage umfassen",
        )
    soll, feiertage = await svc.soll_und_feiertage_laden(session, {ziel_id}, body.von, body.bis)
    tage = svc.abwesenheitstage(
        body.von, body.bis, body.halber_tag_von, body.halber_tag_bis, soll[ziel_id], feiertage
    )
    if not tage:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Im gewählten Zeitraum liegt kein Arbeitstag (Wochenenden, Feiertage und freie Tage zählen nicht)",
        )
    if await svc.hat_ueberschneidung(session, ziel_id, body.von, body.bis):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Im gewählten Zeitraum existiert bereits ein offener oder genehmigter Antrag",
        )

    verwaltet = await _darf_verwalten(auth, session)
    # Krankheit braucht keine Genehmigung; sonst nur, wer verwalten darf.
    direkt = body.art == "krankheit" or verwaltet
    jetzt = datetime.now(timezone.utc)
    antrag = Abwesenheitsantrag(
        mandant_id=auth.mandant_id,
        user_id=ziel_id,
        art=body.art,
        von=body.von,
        bis=body.bis,
        halber_tag_von=body.halber_tag_von,
        halber_tag_bis=body.halber_tag_bis,
        status="genehmigt" if direkt else "offen",
        notiz=body.notiz,
        erstellt_von=auth.user_id,
        bearbeitet_von=auth.user_id if direkt else None,
        bearbeitet_am=jetzt if direkt else None,
    )
    session.add(antrag)
    await session.flush()
    if direkt:
        await svc.zeiteintraege_erzeugen(session, antrag, tage)
    return await _lesen(session, antrag)


@router.get("", response_model=list[AbwesenheitRead])
async def antraege_auflisten(
    user_id: UUID | None = Query(default=None),
    alle: bool = Query(default=False, description="Alle Mitarbeiter des Mandanten (nur mit Berechtigung)"),
    status_filter: AbwesenheitStatus | None = Query(default=None, alias="status"),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    nur_offene: bool = Query(default=False),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AbwesenheitRead]:
    stmt = select(Abwesenheitsantrag)
    if alle:
        await _verwalten_pruefen(auth, session, "Keine Berechtigung, Abwesenheiten aller Mitarbeiter zu sehen")
        if user_id is not None:
            await _user_pruefen(user_id, auth, session)
            stmt = stmt.where(Abwesenheitsantrag.user_id == user_id)
    else:
        ziel_id = await _ziel_user(user_id, auth, session, "Keine Berechtigung, fremde Abwesenheiten zu sehen")
        stmt = stmt.where(Abwesenheitsantrag.user_id == ziel_id)
    if nur_offene:
        stmt = stmt.where(Abwesenheitsantrag.status == "offen")
    elif status_filter is not None:
        stmt = stmt.where(Abwesenheitsantrag.status == status_filter)
    if von is not None:
        stmt = stmt.where(Abwesenheitsantrag.bis >= von)
    if bis is not None:
        stmt = stmt.where(Abwesenheitsantrag.von <= bis)
    antraege = list(
        (await session.execute(stmt.order_by(Abwesenheitsantrag.von.desc(), Abwesenheitsantrag.erstellt_am.desc())))
        .scalars()
        .all()
    )
    return await _antraege_lesen(session, antraege)


@router.post("/{antrag_id}/genehmigen", response_model=AbwesenheitRead)
async def genehmigen(
    antrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AbwesenheitRead:
    await _verwalten_pruefen(auth, session, "Keine Berechtigung zum Genehmigen von Abwesenheiten")
    antrag = await _antrag_laden(antrag_id, session)
    if antrag.status != "offen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nur offene Anträge können genehmigt werden")
    antrag.status = "genehmigt"
    antrag.bearbeitet_von = auth.user_id
    antrag.bearbeitet_am = datetime.now(timezone.utc)
    tage = (await svc.tage_je_antrag(session, [antrag]))[antrag.id]
    await svc.zeiteintraege_erzeugen(session, antrag, tage)
    return await _lesen(session, antrag)


@router.post("/{antrag_id}/ablehnen", response_model=AbwesenheitRead)
async def ablehnen(
    antrag_id: UUID,
    body: AbwesenheitAblehnen | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AbwesenheitRead:
    await _verwalten_pruefen(auth, session, "Keine Berechtigung zum Ablehnen von Abwesenheiten")
    antrag = await _antrag_laden(antrag_id, session)
    if antrag.status != "offen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nur offene Anträge können abgelehnt werden")
    antrag.status = "abgelehnt"
    antwort = body.antwort.strip() if body and body.antwort else None
    antrag.antwort = antwort or None
    antrag.bearbeitet_von = auth.user_id
    antrag.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    return await _lesen(session, antrag)


@router.post("/{antrag_id}/zurueckziehen", response_model=AbwesenheitRead)
async def zurueckziehen(
    antrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AbwesenheitRead:
    antrag = await _antrag_laden(antrag_id, session)
    verwaltet = await _darf_verwalten(auth, session)
    if antrag.user_id != auth.user_id and not verwaltet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abwesenheitsantrag nicht gefunden")
    if antrag.status == "genehmigt":
        if not verwaltet:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Eine genehmigte Abwesenheit kann nur das Büro stornieren",
            )
    elif antrag.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Dieser Antrag ist bereits abgeschlossen"
        )
    if antrag.status == "genehmigt":
        await svc.zeiteintraege_entfernen(session, antrag, auth.user_id)
    antrag.status = "zurueckgezogen"
    antrag.bearbeitet_von = auth.user_id
    antrag.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    return await _lesen(session, antrag)


@router.get("/konto", response_model=UrlaubskontoRead)
async def urlaubskonto(
    user_id: UUID | None = Query(default=None),
    jahr: int | None = Query(default=None, ge=2000, le=2100),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UrlaubskontoRead:
    ziel_id = await _ziel_user(user_id, auth, session, "Keine Berechtigung, fremde Urlaubskonten zu sehen")
    heute = in_lokal(datetime.now(timezone.utc)).date()
    jahr = jahr or heute.year
    anspruch = (
        await session.execute(
            select(Urlaubsanspruch).where(Urlaubsanspruch.user_id == ziel_id, Urlaubsanspruch.jahr == jahr)
        )
    ).scalar_one_or_none()

    antraege = list(
        (
            await session.execute(
                select(Abwesenheitsantrag).where(
                    Abwesenheitsantrag.user_id == ziel_id,
                    Abwesenheitsantrag.art == "urlaub",
                    Abwesenheitsantrag.status.in_(("offen", "genehmigt")),
                    Abwesenheitsantrag.von <= date(jahr, 12, 31),
                    Abwesenheitsantrag.bis >= date(jahr, 1, 1),
                )
            )
        )
        .scalars()
        .all()
    )
    tage = await svc.tage_je_antrag(session, antraege)
    genommen: list[tuple[date, Decimal]] = []
    beantragt: list[tuple[date, Decimal]] = []
    for a in antraege:
        ziel = genommen if a.status == "genehmigt" else beantragt
        ziel.extend((t.datum, t.faktor) for t in tage[a.id] if t.datum.year == jahr)

    konto = svc.berechne_konto(
        anspruch.tage if anspruch else Decimal("0"),
        anspruch.resturlaub_tage if anspruch else Decimal("0"),
        anspruch.resturlaub_verfaellt_am if anspruch else None,
        genommen,
        beantragt,
        heute,
    )
    return UrlaubskontoRead(
        user_id=ziel_id,
        jahr=jahr,
        anspruch=konto.anspruch,
        resturlaub=konto.resturlaub,
        resturlaub_verfaellt_am=anspruch.resturlaub_verfaellt_am if anspruch else None,
        resturlaub_verfallen=konto.resturlaub_verfallen,
        genommen=konto.genommen,
        beantragt=konto.beantragt,
        verbleibend=konto.verbleibend,
    )


@router.put("/anspruch/{user_id}/{jahr}", response_model=UrlaubsanspruchRead)
async def anspruch_setzen(
    user_id: UUID,
    jahr: int,
    body: UrlaubsanspruchSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Urlaubsanspruch:
    await _verwalten_pruefen(auth, session, "Keine Berechtigung zum Pflegen des Urlaubsanspruchs")
    if not 2000 <= jahr <= 2100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Ungültiges Jahr")
    await _user_pruefen(user_id, auth, session)
    zeile = (
        await session.execute(
            select(Urlaubsanspruch).where(Urlaubsanspruch.user_id == user_id, Urlaubsanspruch.jahr == jahr)
        )
    ).scalar_one_or_none()
    if zeile is None:
        zeile = Urlaubsanspruch(mandant_id=auth.mandant_id, user_id=user_id, jahr=jahr)
        session.add(zeile)
    zeile.tage = body.tage
    zeile.resturlaub_tage = body.resturlaub_tage
    zeile.resturlaub_verfaellt_am = body.resturlaub_verfaellt_am
    await session.flush()
    await session.refresh(zeile)
    return zeile


@router.get("/kalender", response_model=list[KalenderEintragRead])
async def kalender(
    von: date,
    bis: date,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[KalenderEintragRead]:
    await _verwalten_pruefen(auth, session, "Keine Berechtigung, die Abwesenheitsübersicht zu sehen")
    if bis < von:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="'bis' liegt vor 'von'")
    if (bis - von).days + 1 > svc.KALENDER_MAX_TAGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Zeitraum darf höchstens {svc.KALENDER_MAX_TAGE} Tage umfassen",
        )
    antraege = list(
        (
            await session.execute(
                select(Abwesenheitsantrag)
                .where(
                    Abwesenheitsantrag.status == "genehmigt",
                    Abwesenheitsantrag.von <= bis,
                    Abwesenheitsantrag.bis >= von,
                )
                .order_by(Abwesenheitsantrag.von, Abwesenheitsantrag.user_id)
            )
        )
        .scalars()
        .all()
    )
    tage = await svc.tage_je_antrag(session, antraege)
    namen = await _namen(session, {a.user_id for a in antraege})
    return [
        KalenderEintragRead(
            id=a.id,
            user_id=a.user_id,
            user_name=namen.get(a.user_id, ""),
            art=a.art,
            von=a.von,
            bis=a.bis,
            halber_tag_von=a.halber_tag_von,
            halber_tag_bis=a.halber_tag_bis,
            tage=svc.summe_tage(tage[a.id]),
        )
        for a in antraege
    ]
