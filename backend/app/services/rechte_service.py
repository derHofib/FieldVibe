from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rollen_recht import MandantRollenRecht

# Code-Defaults, die greifen, solange ein mandant_admin fuer eine
# (rolle, bereich, aktion)-Kombination noch keine eigene Einstellung
# hinterlegt hat (siehe MandantRollenRecht). "mitarbeiter" startet nah am
# bisherigen Verhalten von techniker/disponent (operativ, lesend+schreibend),
# "controller" startet rein lesend -- passend zu einer internen
# Controlling-Rolle ohne operative Eingriffsbefugnis. Beides ist je Mandant
# frei nachjustierbar.
DEFAULT_RECHTE: dict[str, dict[str, set[str]]] = {
    "mitarbeiter": {
        "vorgaenge": {"sehen", "bearbeiten"},
        "kunden": {"sehen", "bearbeiten"},
        "material": {"sehen", "bearbeiten"},
        "dispo": {"sehen"},
        "abrechnung": set(),
        "statistik": {"sehen"},
        "mitarbeiterverwaltung": set(),
    },
    "controller": {
        "vorgaenge": {"sehen"},
        "kunden": {"sehen"},
        "material": {"sehen"},
        "dispo": {"sehen"},
        "abrechnung": {"sehen"},
        "statistik": {"sehen"},
        "mitarbeiterverwaltung": {"sehen"},
    },
}


async def hat_recht(
    session: AsyncSession, *, mandant_id: UUID | None, rolle: str, bereich: str, aktion: str
) -> bool:
    if mandant_id is not None:
        result = await session.execute(
            select(MandantRollenRecht.erlaubt).where(
                MandantRollenRecht.mandant_id == mandant_id,
                MandantRollenRecht.rolle == rolle,
                MandantRollenRecht.bereich == bereich,
                MandantRollenRecht.aktion == aktion,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
    return aktion in DEFAULT_RECHTE.get(rolle, {}).get(bereich, set())


async def rechte_matrix_fuer_mandant(
    session: AsyncSession, mandant_id: UUID
) -> dict[str, dict[str, dict[str, bool]]]:
    """Liefert die vollstaendige, aufgeloeste Matrix (Defaults + Overrides)
    fuer die Admin-Konfigurationsseite -- so sieht ein mandant_admin auf
    einen Blick den tatsaechlich wirksamen Stand, nicht nur die von ihm
    bereits explizit gesetzten Abweichungen."""
    matrix: dict[str, dict[str, dict[str, bool]]] = {
        rolle: {
            bereich: {aktion: aktion in DEFAULT_RECHTE[rolle][bereich] for aktion in ("sehen", "bearbeiten")}
            for bereich in DEFAULT_RECHTE[rolle]
        }
        for rolle in DEFAULT_RECHTE
    }
    result = await session.execute(
        select(MandantRollenRecht).where(MandantRollenRecht.mandant_id == mandant_id)
    )
    for row in result.scalars().all():
        matrix.setdefault(row.rolle, {}).setdefault(row.bereich, {})[row.aktion] = row.erlaubt
    return matrix
