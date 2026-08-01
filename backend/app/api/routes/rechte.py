from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.rollen_recht import MandantRollenRecht
from app.schemas.rollen_recht import RechteMatrixEintrag, RechtSetzen
from app.services.rechte_service import rechte_matrix_fuer_mandant

router = APIRouter(
    prefix="/api/rechte-matrix",
    tags=["rechte-matrix"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)


def _als_liste(matrix: dict[str, dict[str, dict[str, bool]]]) -> list[RechteMatrixEintrag]:
    return [
        RechteMatrixEintrag(rolle=rolle, bereich=bereich, aktion=aktion, erlaubt=erlaubt)
        for rolle, bereiche in matrix.items()
        for bereich, aktionen in bereiche.items()
        for aktion, erlaubt in aktionen.items()
    ]


@router.get("", response_model=list[RechteMatrixEintrag])
async def get_rechte_matrix(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    matrix = await rechte_matrix_fuer_mandant(session, auth.mandant_id)
    return _als_liste(matrix)


@router.put("", response_model=list[RechteMatrixEintrag])
async def set_recht(
    body: RechtSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    result = await session.execute(
        select(MandantRollenRecht).where(
            MandantRollenRecht.mandant_id == auth.mandant_id,
            MandantRollenRecht.rolle == body.rolle,
            MandantRollenRecht.bereich == body.bereich,
            MandantRollenRecht.aktion == body.aktion,
        )
    )
    eintrag = result.scalar_one_or_none()
    if eintrag is None:
        session.add(
            MandantRollenRecht(
                mandant_id=auth.mandant_id,
                rolle=body.rolle,
                bereich=body.bereich,
                aktion=body.aktion,
                erlaubt=body.erlaubt,
            )
        )
    else:
        eintrag.erlaubt = body.erlaubt
    await session.flush()

    matrix = await rechte_matrix_fuer_mandant(session, auth.mandant_id)
    return _als_liste(matrix)
