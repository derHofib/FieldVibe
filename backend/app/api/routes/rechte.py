from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, require_roles
from app.core.rechte_registry import SCOPES, alle_bereiche
from app.schemas.rechte import RechteBereichRead, RechteRegistryRead

# Kundenportal-/Partner-Zugaenge haben eigene Auth und sind hier nicht zugelassen
# (require_roles prueft ausschliesslich Mitarbeiter-Rollen).
router = APIRouter(prefix="/api/rechte", tags=["rechte"])


@router.get("/registry", response_model=RechteRegistryRead)
async def get_registry(
    _: AuthContext = Depends(
        require_roles("super_admin", "mandant_admin", "custom", "loesch_ansicht", "loesch_operativ")
    ),
) -> RechteRegistryRead:
    return RechteRegistryRead(
        bereiche=[
            RechteBereichRead(
                key=b.key, label=b.label, aktionen=list(b.aktionen), scopes=list(b.scopes), modul=b.modul
            )
            for b in alle_bereiche()
        ],
        scopes=list(SCOPES),
    )
