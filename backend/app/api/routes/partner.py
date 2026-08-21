from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.core.security import hash_password
from app.models.einladung import Einladung
from app.models.partner import Partner
from app.models.partner_nachweis import PartnerNachweis
from app.models.partner_zugang import PartnerZugang
from app.models.user import User
from app.schemas.einladung import EinladungRead, PartnerEinladungCreate
from app.schemas.partner import (
    PartnerCreate,
    PartnerNachweisCreate,
    PartnerNachweisRead,
    PartnerNachweisUpdate,
    PartnerNachweisUploadResponse,
    PartnerNachweisUrl,
    PartnerRead,
    PartnerUpdate,
    PartnerZugangRead,
    PartnerZugangUpdate,
)
from app.services import storage_service
from app.services.einladung_service import (
    create_einladung,
    registrierungslink_erzeugen,
    to_read_model,
    versende_einladung,
)

_NACHWEIS_MAX_BYTES = 15 * 1024 * 1024

# Eigener Rechte-Bereich "partner" (Migration 0070) statt der vormaligen
# require_roles(..., "disponent", "techniker") -- diese Rollen-Literale gibt
# es seit der Rechte-Matrix/account_typ-Umstellung als tatsaechlichen
# User.role-Wert nicht mehr (jeder Mitarbeiter-Account laeuft ueber
# role="custom"), der Bereich war dadurch fuer keinen account_typ-basierten
# Nutzer erreichbar. loesch_operativ hat ueberall dieselben Rechte wie
# mandant_admin (siehe app/api/deps.py:require_roles()) und braucht daher wie
# dieser Zugriff auf diesen Router.
router = APIRouter(
    prefix="/api/partner",
    tags=["partner"],
    dependencies=[
        Depends(require_module("nachunternehmer")),
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
    ],
)


def _nachweis_to_read(nachweis: PartnerNachweis) -> PartnerNachweisRead:
    return PartnerNachweisRead(
        id=nachweis.id,
        partner_id=nachweis.partner_id,
        typ=nachweis.typ,
        gueltig_bis=nachweis.gueltig_bis,
        dokument_s3_key=nachweis.dokument_s3_key,
        notiz=nachweis.notiz,
        abgelaufen=nachweis.gueltig_bis is not None and nachweis.gueltig_bis < date.today(),
        created_at=nachweis.created_at,
        updated_at=nachweis.updated_at,
    )


@router.get(
    "",
    response_model=list[PartnerRead],
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def list_partner(
    q: str | None = Query(default=None, description="Suche in Name/Gewerk"),
    session: AsyncSession = Depends(get_db),
) -> list[Partner]:
    stmt = select(Partner).order_by(Partner.name)
    if q:
        stmt = stmt.where(Partner.name.ilike(f"%{q}%") | Partner.gewerk.ilike(f"%{q}%"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=PartnerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "erstellen")),
    ],
)
async def create_partner(
    body: PartnerCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Partner:
    # mode="json" statt des Standard-model_dump(): ansprechpartner enthaelt
    # verschachtelte AnsprechpartnerEintrag-Objekte, deren id ein UUID-Objekt
    # ist -- die JSONB-Spalte braucht dafuer JSON-taugliche Werte, siehe
    # create_kunde in app/api/routes/kunden.py fuer dasselbe Muster.
    partner = Partner(mandant_id=auth.mandant_id, **body.model_dump(mode="json"))
    session.add(partner)
    await session.flush()
    return partner


@router.get(
    "/{partner_id}",
    response_model=PartnerRead,
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def get_partner(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    return partner


@router.patch(
    "/{partner_id}",
    response_model=PartnerRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "bearbeiten")),
    ],
)
async def update_partner(
    partner_id: UUID, body: PartnerUpdate, session: AsyncSession = Depends(get_db)
) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    # mode="json" -- siehe create_partner oben.
    changes = body.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(partner, field, value)
    await session.flush()
    if changes:
        await session.refresh(partner)
    return partner


@router.delete(
    "/{partner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("partner", "loeschen")),
    ],
)
async def delete_partner(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    # Nachweise/Zugaenge sind reine Anhaengsel (ondelete=CASCADE in der
    # Migration), Vorgaenge mit gesetztem partner_id blockieren die Loeschung
    # bewusst (kein ondelete auf vorgaenge.partner_id) -- exakt dasselbe
    # Restrict-Verhalten wie bei Kunde/Anlage (siehe kunden.py).
    try:
        await session.delete(partner)
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Partner kann nicht gelöscht werden, da noch Vorgänge zugewiesen sind -- stattdessen deaktivieren.",
        ) from exc


@router.get(
    "/{partner_id}/nachweise",
    response_model=list[PartnerNachweisRead],
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def list_nachweise(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> list[PartnerNachweisRead]:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    result = await session.execute(
        select(PartnerNachweis).where(PartnerNachweis.partner_id == partner_id).order_by(PartnerNachweis.typ)
    )
    return [_nachweis_to_read(n) for n in result.scalars().all()]


@router.post(
    "/{partner_id}/nachweise",
    response_model=PartnerNachweisRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "erstellen")),
    ],
)
async def create_nachweis(
    partner_id: UUID,
    body: PartnerNachweisCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisRead:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    nachweis = PartnerNachweis(mandant_id=auth.mandant_id, partner_id=partner_id, **body.model_dump())
    session.add(nachweis)
    await session.flush()
    return _nachweis_to_read(nachweis)


@router.patch(
    "/{partner_id}/nachweise/{nachweis_id}",
    response_model=PartnerNachweisRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "bearbeiten")),
    ],
)
async def update_nachweis(
    partner_id: UUID,
    nachweis_id: UUID,
    body: PartnerNachweisUpdate,
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisRead:
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachweis nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(nachweis, field, value)
    await session.flush()
    if changes:
        await session.refresh(nachweis)
    return _nachweis_to_read(nachweis)


@router.delete(
    "/{partner_id}/nachweise/{nachweis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("partner", "loeschen")),
    ],
)
async def delete_nachweis(
    partner_id: UUID, nachweis_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachweis nicht gefunden")
    await session.delete(nachweis)
    await session.flush()


@router.post(
    "/{partner_id}/nachweise/{nachweis_id}/upload",
    response_model=PartnerNachweisUploadResponse,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "bearbeiten")),
    ],
)
async def upload_nachweis_dokument(
    partner_id: UUID,
    nachweis_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisUploadResponse:
    # Object-Key wird serverseitig generiert statt vom Client entgegengenommen
    # -- ein clientseitig frei waehlbarer Key haette sonst ohne Aufwand auf
    # ein fremdes Objekt (z.B. eines anderen Mandanten) zeigen koennen,
    # sobald ein Download dafuer existiert. Analog zu app/api/routes/
    # boards.py:upload_board_anhang.
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachweis nicht gefunden")

    data = await file.read()
    if len(data) > _NACHWEIS_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 15 MB)"
        )

    alter_key = nachweis.dokument_s3_key
    key = storage_service.new_partner_nachweis_key(partner_id, file.filename or "nachweis")
    await storage_service.upload_bytes(key, data, file.content_type or "application/octet-stream")
    nachweis.dokument_s3_key = key
    await session.flush()

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return PartnerNachweisUploadResponse(dokument_s3_key=key)


@router.get(
    "/{partner_id}/nachweise/{nachweis_id}/url",
    response_model=PartnerNachweisUrl,
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def get_nachweis_url(
    partner_id: UUID,
    nachweis_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisUrl:
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id or nachweis.dokument_s3_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Dokument hinterlegt")
    return PartnerNachweisUrl(url=storage_service.presigned_get_url(nachweis.dokument_s3_key))


@router.get(
    "/{partner_id}/zugaenge",
    response_model=list[PartnerZugangRead],
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def list_zugaenge(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> list[PartnerZugang]:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    result = await session.execute(select(PartnerZugang).where(PartnerZugang.partner_id == partner_id))
    return list(result.scalars().all())


@router.get(
    "/{partner_id}/einladungen",
    response_model=list[EinladungRead],
    dependencies=[Depends(require_recht("partner", "sehen"))],
)
async def list_partner_einladungen(
    partner_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[EinladungRead]:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    result = await session.execute(
        select(Einladung)
        .where(Einladung.art == "partner", Einladung.partner_id == partner_id)
        .order_by(Einladung.created_at.desc())
    )
    return [
        EinladungRead(
            **to_read_model(
                e, registrierungslink=registrierungslink_erzeugen(e) if e.status == "offen" else None
            )
        )
        for e in result.scalars().all()
    ]


@router.post(
    "/{partner_id}/einladungen",
    response_model=EinladungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "erstellen")),
    ],
)
async def partner_einladen(
    partner_id: UUID,
    body: PartnerEinladungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    einladung = await create_einladung(
        session,
        mandant_id=auth.mandant_id,
        email=body.email,
        art="partner",
        partner_id=partner_id,
        eingeladen_von=auth.user_id,
    )
    await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else partner.name,
        absender_rolle=einladender.role if einladender else None,
    )
    link = registrierungslink_erzeugen(einladung)
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.post(
    "/{partner_id}/einladungen/{einladung_id}/erneut-senden",
    response_model=EinladungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "erstellen")),
    ],
)
async def partner_einladung_erneut_senden(
    partner_id: UUID,
    einladung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    einladung = await session.get(Einladung, einladung_id)
    if (
        einladung is None
        or einladung.art != "partner"
        or einladung.partner_id != partner_id
        or einladung.status != "offen"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else "",
        absender_rolle=einladender.role if einladender else None,
    )
    link = registrierungslink_erzeugen(einladung)
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.delete(
    "/{partner_id}/einladungen/{einladung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("partner", "loeschen")),
    ],
)
async def partner_einladung_widerrufen(
    partner_id: UUID, einladung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    einladung = await session.get(Einladung, einladung_id)
    if (
        einladung is None
        or einladung.art != "partner"
        or einladung.partner_id != partner_id
        or einladung.status != "offen"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")
    einladung.status = "widerrufen"
    await session.flush()


@router.patch(
    "/{partner_id}/zugaenge/{zugang_id}",
    response_model=PartnerZugangRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("partner", "bearbeiten")),
    ],
)
async def update_zugang(
    partner_id: UUID,
    zugang_id: UUID,
    body: PartnerZugangUpdate,
    session: AsyncSession = Depends(get_db),
) -> PartnerZugang:
    zugang = await session.get(PartnerZugang, zugang_id)
    if zugang is None or zugang.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(zugang, field, value)
    if body.password is not None:
        if len(body.password) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwort muss mindestens 10 Zeichen haben",
            )
        zugang.password_hash = hash_password(body.password)
        changes["password_hash"] = zugang.password_hash

    await session.flush()
    if changes:
        await session.refresh(zugang)
    return zugang
