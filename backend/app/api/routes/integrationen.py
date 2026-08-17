from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.security import encrypt_secret
from app.models.integration import MandantIntegration
from app.schemas.integration import (
    MandantIntegrationCreate,
    MandantIntegrationRead,
    MandantIntegrationUpdate,
)

router = APIRouter(
    prefix="/api/integrationen",
    tags=["integrationen"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)

# Der Slot in mandant_integrationen existiert seit Phase 1 fuer beliebige
# zukuenftige Integrationen (Abschnitt 7.4). Angebunden: SMTP (Versand,
# siehe app/services/email_service.py) und IMAP (Rechnungseingang-Import,
# siehe app/services/email_ingest_service.py -- config erwartet
# {"host", "port", "user", "mailbox"}, secret ist das Postfach-Passwort).
# Eine echte Buchhaltungs-API-Anbindung (lexoffice/sevdesk o. ae.) ohne
# echte Zugangsdaten/API-Dokumentation zu bauen waere geraten statt
# fundiert -- bleibt bewusst offen, bis eine konkrete Integration ansteht.
ERLAUBTE_TYPEN = ("smtp", "imap")


def _to_read_model(integration: MandantIntegration) -> MandantIntegrationRead:
    return MandantIntegrationRead(
        id=integration.id,
        mandant_id=integration.mandant_id,
        typ=integration.typ,
        config=integration.config,
        aktiv=integration.aktiv,
        hat_secret=integration.secret_ref is not None,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get("", response_model=list[MandantIntegrationRead])
async def list_integrationen(session: AsyncSession = Depends(get_db)) -> list[MandantIntegrationRead]:
    result = await session.execute(select(MandantIntegration).order_by(MandantIntegration.typ))
    return [_to_read_model(i) for i in result.scalars().all()]


@router.post("", response_model=MandantIntegrationRead, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: MandantIntegrationCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MandantIntegrationRead:
    if body.typ not in ERLAUBTE_TYPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter Integrationstyp: {body.typ}",
        )
    integration = MandantIntegration(
        mandant_id=auth.mandant_id,
        typ=body.typ,
        config=body.config,
        secret_ref=encrypt_secret(body.secret) if body.secret else None,
        aktiv=body.aktiv,
    )
    session.add(integration)
    await session.flush()
    await session.refresh(integration)
    return _to_read_model(integration)


@router.patch("/{integration_id}", response_model=MandantIntegrationRead)
async def update_integration(
    integration_id: UUID,
    body: MandantIntegrationUpdate,
    session: AsyncSession = Depends(get_db),
) -> MandantIntegrationRead:
    integration = await session.get(MandantIntegration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"secret"})
    for field, value in changes.items():
        setattr(integration, field, value)
    # "secret" separat behandelt: nur wenn der Client den Key ueberhaupt
    # mitgeschickt hat (auch mit Wert null, um es zu loeschen) -- sonst
    # wuerde ein Update, das nur "aktiv" aendern will, das bestehende
    # Secret unbeabsichtigt loeschen.
    if "secret" in body.model_fields_set:
        integration.secret_ref = encrypt_secret(body.secret) if body.secret else None

    await session.flush()
    await session.refresh(integration)
    return _to_read_model(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(integration_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    integration = await session.get(MandantIntegration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration nicht gefunden")
    await session.delete(integration)
    await session.flush()
