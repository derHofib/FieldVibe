from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.schemas.system import SystemResourcesRead
from app.services.system_resources_service import get_current_and_history

router = APIRouter(
    prefix="/api/admin/system",
    tags=["super-admin: system"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("/resources", response_model=SystemResourcesRead)
async def get_system_resources() -> dict:
    return get_current_and_history()
