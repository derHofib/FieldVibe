from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.schemas.version import VersionInfo
from app.services.version_service import get_version_info

router = APIRouter(
    prefix="/api/admin/version",
    tags=["super-admin: version"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("", response_model=VersionInfo)
async def version() -> VersionInfo:
    return await get_version_info()
