from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AuthContext, require_roles
from app.core.config import get_settings
from app.core.security import create_impersonation_token
from app.db.session import system_session
from app.models.mandant import Mandant
from app.schemas.auth import ImpersonateResponse
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/admin", tags=["super-admin: impersonation"])
_settings = get_settings()


@router.post(
    "/mandanten/{mandant_id}/impersonate",
    response_model=ImpersonateResponse,
    dependencies=[Depends(require_roles("super_admin"))],
)
async def impersonate_mandant(
    mandant_id: UUID,
    auth: AuthContext = Depends(require_roles("super_admin")),
) -> ImpersonateResponse:
    """Issues a short-lived, mandant_admin-scoped token for support access.

    The resulting token keeps the super_admin's own user id as `sub` so that
    every action taken while impersonating is attributed to the real actor
    in audit_log -- it just downgrades the role and pins the mandant, which
    is what actually puts RLS in effect for the rest of the session.
    """
    async with system_session() as session:
        mandant = await session.get(Mandant, mandant_id)
        if mandant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden"
            )

        await log_action(
            session,
            aktion="login_als_mandant",
            mandant_id=mandant.id,
            actor_user_id=auth.user_id,
            entity_type="mandant",
            entity_id=mandant.id,
            payload={"mandant_name": mandant.name},
        )

        token = create_impersonation_token(
            subject=auth.user_id,
            role="mandant_admin",
            mandant_id=mandant.id,
            impersonated_by=auth.user_id,
        )
        return ImpersonateResponse(
            access_token=token,
            mandant_id=mandant.id,
            expires_in_minutes=_settings.impersonation_token_expire_minutes,
        )
