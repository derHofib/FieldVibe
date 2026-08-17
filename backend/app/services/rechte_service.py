from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import RECHTE_AKTIONEN, RECHTE_BEREICHE, AccountTyp, AccountTypRecht


async def ist_auf_zugewiesene_kunden_beschraenkt(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None
) -> bool:
    """Ersetzt die vormals an den Rollennamen 'techniker' gebundene
    Einschraenkung 'sieht nur zugewiesene Kunden' -- jetzt ein Schalter je
    Account-Typ (siehe app/models/account_typ.py:AccountTyp.nur_zugewiesene_kunden).
    Nimmt role/account_typ_id statt eines AuthContext entgegen, um einen
    zirkulaeren Import mit app.api.deps (das hat_recht aus diesem Modul
    importiert) zu vermeiden."""
    if role != "custom" or account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.nur_zugewiesene_kunden


async def darf_vorgang_selbst_uebernehmen(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None
) -> bool:
    """Steuert den "Ticket übernehmen"-Button auf der Vorgang-Detailseite
    (siehe app/api/routes/vorgaenge.py:uebernehmen). mandant_admin/super_admin
    duerfen immer selbst uebernehmen; fuer role='custom' ist es ein Schalter
    je Account-Typ (siehe app/models/account_typ.py:
    AccountTyp.darf_vorgaenge_selbst_uebernehmen), damit ein mandant_admin
    selbstaendigen Technikern das erlauben und weniger selbstaendigen
    stattdessen manuell zuweisen kann."""
    if role != "custom":
        return True
    if account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.darf_vorgaenge_selbst_uebernehmen


async def darf_fremde_mitarbeiterdaten_einsehen(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None
) -> bool:
    """Ersetzt die vormals an den Rollennamen 'techniker' gebundene
    Einschraenkung 'sieht nur die eigene Zeiterfassung/Statistik' (siehe
    app/api/routes/zeiterfassung.py). Bewusst getrennt von
    mitarbeiterverwaltung.sehen, das nur den @-Erwaehnungs-Picker in
    app/api/routes/users.py:list_users abdeckt und keine Einsicht in
    personenbezogene Arbeitszeiten einraeumen soll."""
    if role != "custom":
        return True
    return await hat_recht(
        session, account_typ_id=account_typ_id, bereich="mitarbeiterverwaltung", aktion="bearbeiten"
    )


async def hat_recht(
    session: AsyncSession, *, account_typ_id: UUID | None, bereich: str, aktion: str
) -> bool:
    if account_typ_id is None:
        return False
    result = await session.execute(
        select(AccountTypRecht.erlaubt).where(
            AccountTypRecht.account_typ_id == account_typ_id,
            AccountTypRecht.bereich == bereich,
            AccountTypRecht.aktion == aktion,
        )
    )
    row = result.scalar_one_or_none()
    return bool(row)


async def rechte_matrix_fuer_account_typ(
    session: AsyncSession, account_typ_id: UUID
) -> dict[str, dict[str, bool]]:
    """Vollstaendig aufgeloeste Matrix (jede Bereich/Aktion-Kombination,
    fehlende Zeilen = False) fuer die Account-Typen-Verwaltungsseite."""
    matrix: dict[str, dict[str, bool]] = {
        bereich: {aktion: False for aktion in RECHTE_AKTIONEN} for bereich in RECHTE_BEREICHE
    }
    result = await session.execute(
        select(AccountTypRecht).where(AccountTypRecht.account_typ_id == account_typ_id)
    )
    for row in result.scalars().all():
        matrix.setdefault(row.bereich, {})[row.aktion] = row.erlaubt
    return matrix
