from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungPosition, EingangsrechnungZahlung
from app.models.lieferant import Lieferant
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.eingangsrechnung import (
    EingangsrechnungCreate,
    EingangsrechnungPositionCreate,
    EingangsrechnungRead,
    EingangsrechnungUpdate,
    EingangsrechnungZahlungCreate,
)
from app.services import papierkorb_service, storage_service
from app.services.csv_service import csv_response
from app.services.eingangsrechnung_service import (
    bezahlter_betrag,
    brutto_betrag,
    positionen_fuer,
    to_read_model,
    zahlungen_fuer,
)

router = APIRouter(
    prefix="/api/eingangsrechnungen",
    tags=["eingangsrechnungen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_module("abrechnung")),
        Depends(require_recht("abrechnung", "sehen")),
    ],
)

_GUELTIGE_UEBERGAENGE = {"offen": {"bezahlt", "storniert"}}
_BELEG_MAX_BYTES = 10 * 1024 * 1024


@router.get("", response_model=list[EingangsrechnungRead])
async def list_eingangsrechnungen(
    lieferant_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    kategorie: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[EingangsrechnungRead]:
    stmt = (
        select(Eingangsrechnung)
        .where(Eingangsrechnung.geloescht_am.is_(None))
        .order_by(Eingangsrechnung.rechnungsdatum.desc())
    )
    if lieferant_id:
        stmt = stmt.where(Eingangsrechnung.lieferant_id == lieferant_id)
    if vorgang_id:
        stmt = stmt.where(Eingangsrechnung.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(Eingangsrechnung.status == status_filter)
    if kategorie:
        stmt = stmt.where(Eingangsrechnung.kategorie == kategorie)
    result = await session.execute(stmt)
    return [await to_read_model(session, e) for e in result.scalars().all()]


@router.get("/export/csv")
async def export_eingangsrechnungen_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> Response:
    stmt = (
        select(Eingangsrechnung)
        .where(Eingangsrechnung.geloescht_am.is_(None))
        .order_by(Eingangsrechnung.rechnungsdatum.desc())
    )
    if status_filter:
        stmt = stmt.where(Eingangsrechnung.status == status_filter)
    eingangsrechnungen = (await session.execute(stmt)).scalars().all()

    rows = []
    for e in eingangsrechnungen:
        positionen = await positionen_fuer(session, e.id)
        zahlungen = await zahlungen_fuer(session, e.id)
        brutto = brutto_betrag(e, positionen)
        rows.append(
            [
                e.lieferant_name,
                e.rechnungsnummer_lieferant,
                e.rechnungsdatum.strftime("%d.%m.%Y"),
                e.faellig_am.strftime("%d.%m.%Y") if e.faellig_am else "",
                e.kategorie or "",
                e.status,
                str(brutto),
                str(bezahlter_betrag(zahlungen)),
                str(brutto - bezahlter_betrag(zahlungen)),
            ]
        )

    return csv_response(
        ["Lieferant", "Rechnungsnummer", "Rechnungsdatum", "Fällig am", "Kategorie", "Status", "Brutto", "Bezahlt", "Offen"],
        rows,
        "Eingangsrechnungen.csv",
    )


@router.get("/{eingangsrechnung_id}", response_model=EingangsrechnungRead)
async def get_eingangsrechnung(
    eingangsrechnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    return await to_read_model(session, eingangsrechnung)


@router.delete(
    "/{eingangsrechnung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("abrechnung", "loeschen")),
    ],
)
async def delete_eingangsrechnung(
    eingangsrechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    if eingangsrechnung.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur offene Eingangsrechnungen können gelöscht werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="eingangsrechnung", entity_id=eingangsrechnung_id, actor_user_id=auth.user_id
    )


def _neue_positionen(
    eingangsrechnung_id: UUID, mandant_id: UUID, eintraege: list[EingangsrechnungPositionCreate]
) -> list[EingangsrechnungPosition]:
    return [
        EingangsrechnungPosition(
            mandant_id=mandant_id,
            eingangsrechnung_id=eingangsrechnung_id,
            position=i + 1,
            beschreibung=e.beschreibung,
            menge=e.menge,
            einheit=e.einheit,
            einzelpreis=e.einzelpreis,
        )
        for i, e in enumerate(eintraege)
    ]


@router.post(
    "",
    response_model=EingangsrechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "erstellen")),
    ],
)
async def create_eingangsrechnung(
    body: EingangsrechnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EingangsrechnungRead:
    lieferant_name = body.lieferant_name
    if body.lieferant_id is not None:
        lieferant = await session.get(Lieferant, body.lieferant_id)
        if lieferant is None or lieferant.geloescht_am is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lieferant nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        lieferant_name = lieferant.name
    elif not lieferant_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lieferant_name ist ohne lieferant_id erforderlich",
        )

    if body.vorgang_id is not None:
        vorgang = await session.get(Vorgang, body.vorgang_id)
        if vorgang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    eingangsrechnung = Eingangsrechnung(
        mandant_id=auth.mandant_id,
        lieferant_id=body.lieferant_id,
        lieferant_name=lieferant_name,
        vorgang_id=body.vorgang_id,
        rechnungsnummer_lieferant=body.rechnungsnummer_lieferant,
        rechnungsdatum=body.rechnungsdatum,
        faellig_am=body.faellig_am,
        betrag_netto=body.betrag_netto,
        mwst_satz=body.mwst_satz,
        skonto_prozent=body.skonto_prozent,
        skonto_tage=body.skonto_tage,
        kategorie=body.kategorie,
        notiz=body.notiz,
        erstellt_von=auth.user_id,
    )
    session.add(eingangsrechnung)
    await session.flush()

    for p in _neue_positionen(eingangsrechnung.id, auth.mandant_id, body.positionen):
        session.add(p)
    await session.flush()
    await session.refresh(eingangsrechnung)
    return await to_read_model(session, eingangsrechnung)


@router.post(
    "/{eingangsrechnung_id}/positionen",
    response_model=EingangsrechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def add_position(
    eingangsrechnung_id: UUID,
    body: EingangsrechnungPositionCreate,
    session: AsyncSession = Depends(get_db),
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    if eingangsrechnung.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur bei offenen Rechnungen ergänzt werden"
        )

    bestehende = await positionen_fuer(session, eingangsrechnung_id)
    naechste_position = max((p.position for p in bestehende), default=0) + 1
    session.add(
        EingangsrechnungPosition(
            mandant_id=eingangsrechnung.mandant_id,
            eingangsrechnung_id=eingangsrechnung_id,
            position=naechste_position,
            beschreibung=body.beschreibung,
            menge=body.menge,
            einheit=body.einheit,
            einzelpreis=body.einzelpreis,
        )
    )
    await session.flush()
    await session.refresh(eingangsrechnung)
    return await to_read_model(session, eingangsrechnung)


@router.patch(
    "/{eingangsrechnung_id}",
    response_model=EingangsrechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def update_eingangsrechnung(
    eingangsrechnung_id: UUID,
    body: EingangsrechnungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")

    if body.betrag_netto is not None:
        if eingangsrechnung.status != "offen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Betrag kann nur bei offenen Rechnungen geändert werden"
            )
        bestehende_positionen = await positionen_fuer(session, eingangsrechnung_id)
        if bestehende_positionen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diese Rechnung hat eigene Positionen -- der Betrag ergibt sich aus deren Summe",
            )
        eingangsrechnung.betrag_netto = body.betrag_netto
    if body.faellig_am is not None:
        eingangsrechnung.faellig_am = body.faellig_am
    if body.skonto_prozent is not None or body.skonto_tage is not None:
        if eingangsrechnung.status != "offen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Skonto kann nur bei offenen Rechnungen geändert werden"
            )
        if body.skonto_prozent is not None:
            eingangsrechnung.skonto_prozent = body.skonto_prozent
        if body.skonto_tage is not None:
            eingangsrechnung.skonto_tage = body.skonto_tage
    if body.kategorie is not None:
        eingangsrechnung.kategorie = body.kategorie
    if body.notiz is not None:
        eingangsrechnung.notiz = body.notiz

    neuer_status = body.status
    if neuer_status is not None:
        if neuer_status not in _GUELTIGE_UEBERGAENGE.get(eingangsrechnung.status, set()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Statuswechsel von '{eingangsrechnung.status}' nach '{neuer_status}' nicht erlaubt",
            )
        if neuer_status == "bezahlt":
            eingangsrechnung.bezahlt_am = datetime.now(timezone.utc)
        eingangsrechnung.status = neuer_status

        if eingangsrechnung.vorgang_id is not None:
            session.add(
                VorgangEvent(
                    mandant_id=auth.mandant_id,
                    vorgang_id=eingangsrechnung.vorgang_id,
                    event_type="eingangsrechnung_status",
                    author_user_id=auth.user_id,
                    body=(
                        f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} "
                        f"({eingangsrechnung.lieferant_name}): Status '{neuer_status}'"
                    ),
                    payload={"eingangsrechnung_id": str(eingangsrechnung.id), "status": neuer_status},
                )
            )

    await session.flush()
    await session.refresh(eingangsrechnung)
    return await to_read_model(session, eingangsrechnung)


@router.post(
    "/{eingangsrechnung_id}/zahlungen",
    response_model=EingangsrechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def add_zahlung(
    eingangsrechnung_id: UUID,
    body: EingangsrechnungZahlungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    if eingangsrechnung.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Zahlungen sind nur bei offenen Rechnungen möglich"
        )
    if body.betrag <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zahlungsbetrag muss positiv sein")

    positionen = await positionen_fuer(session, eingangsrechnung_id)
    zahlungen = await zahlungen_fuer(session, eingangsrechnung_id)
    brutto = brutto_betrag(eingangsrechnung, positionen)
    offener_betrag = brutto - bezahlter_betrag(zahlungen)
    if body.betrag > offener_betrag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zahlung übersteigt den offenen Betrag ({offener_betrag} EUR)",
        )

    session.add(
        EingangsrechnungZahlung(
            mandant_id=eingangsrechnung.mandant_id,
            eingangsrechnung_id=eingangsrechnung_id,
            betrag=body.betrag,
            datum=body.datum or date.today(),
            erstellt_von=auth.user_id,
        )
    )
    await session.flush()

    verbleibt = offener_betrag - body.betrag
    if verbleibt <= 0:
        eingangsrechnung.status = "bezahlt"
        eingangsrechnung.bezahlt_am = datetime.now(timezone.utc)

    if eingangsrechnung.vorgang_id is not None:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=eingangsrechnung.vorgang_id,
                event_type="eingangsrechnung_status",
                author_user_id=auth.user_id,
                body=(
                    f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} "
                    f"({eingangsrechnung.lieferant_name}): Zahlung über {body.betrag} EUR erfasst"
                ),
                payload={"eingangsrechnung_id": str(eingangsrechnung.id), "betrag": str(body.betrag)},
            )
        )

    await session.flush()
    await session.refresh(eingangsrechnung)
    return await to_read_model(session, eingangsrechnung)


@router.post(
    "/{eingangsrechnung_id}/beleg",
    response_model=EingangsrechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def upload_beleg(
    eingangsrechnung_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    if not file.content_type or not (
        file.content_type.startswith("image/") or file.content_type == "application/pdf"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur PDF- oder Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > _BELEG_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 10 MB)")

    alter_key = eingangsrechnung.beleg_object_key
    key = storage_service.new_eingangsrechnung_beleg_key(eingangsrechnung.id, file.filename or "beleg.pdf")
    await storage_service.upload_bytes(key, data, file.content_type)
    eingangsrechnung.beleg_object_key = key
    await session.flush()
    await session.refresh(eingangsrechnung)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return await to_read_model(session, eingangsrechnung)


@router.get("/{eingangsrechnung_id}/beleg-url")
async def get_beleg_url(
    eingangsrechnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> dict[str, str | None]:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    if eingangsrechnung.beleg_object_key is None:
        return {"url": None}
    return {"url": storage_service.presigned_get_url(eingangsrechnung.beleg_object_key)}


@router.delete(
    "/{eingangsrechnung_id}/beleg",
    response_model=EingangsrechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def remove_beleg(
    eingangsrechnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> EingangsrechnungRead:
    eingangsrechnung = await session.get(Eingangsrechnung, eingangsrechnung_id)
    if eingangsrechnung is None or eingangsrechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eingangsrechnung nicht gefunden")
    alter_key = eingangsrechnung.beleg_object_key
    eingangsrechnung.beleg_object_key = None
    await session.flush()
    await session.refresh(eingangsrechnung)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return await to_read_model(session, eingangsrechnung)
