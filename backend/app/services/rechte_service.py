from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import RECHTE_BEREICHE, AccountTyp, AccountTypRecht, aktionen_fuer_bereich
from app.services import berechtigung_service


# Aufloesung fuer Nutzer: mit user_id laufen die Funktionen ueber die Rechte-Engine
# (berechtigung_service, aktive Besetzungen im Organigramm). Ohne user_id gilt der
# Altpfad ueber users.account_typ_id (Referenz fuer den Golden-Test und fuer
# Aufrufer, die noch nicht umgestellt sind). Die Typ-Matrix-Funktionen unten
# (hat_recht ohne user_id, rechte_matrix_fuer_account_typ) bleiben fuer die
# Account-Typ-Verwaltung.


async def ist_auf_zugewiesene_kunden_beschraenkt(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None, user_id: UUID | None = None
) -> bool:
    """Ersetzt die vormals an den Rollennamen 'techniker' gebundene
    Einschraenkung 'sieht nur zugewiesene Kunden' -- jetzt ein Schalter je
    Account-Typ (siehe app/models/account_typ.py:AccountTyp.nur_zugewiesene_kunden).
    Nimmt role/account_typ_id statt eines AuthContext entgegen, um einen
    zirkulaeren Import mit app.api.deps (das hat_recht aus diesem Modul
    importiert) zu vermeiden."""
    if user_id is not None:
        return await berechtigung_service.ist_auf_zugewiesene_kunden_beschraenkt(
            session, user_id=user_id, rolle=role
        )
    if role != "custom" or account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.nur_zugewiesene_kunden


async def darf_vorgang_selbst_uebernehmen(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None, user_id: UUID | None = None
) -> bool:
    """Steuert den "Ticket übernehmen"-Button auf der Vorgang-Detailseite
    (siehe app/api/routes/vorgaenge.py:uebernehmen). mandant_admin/super_admin
    duerfen immer selbst uebernehmen; fuer role='custom' ist es ein Schalter
    je Account-Typ (siehe app/models/account_typ.py:
    AccountTyp.darf_vorgaenge_selbst_uebernehmen), damit ein mandant_admin
    selbstaendigen Technikern das erlauben und weniger selbstaendigen
    stattdessen manuell zuweisen kann."""
    if user_id is not None:
        return await berechtigung_service.flag_von(
            session, user_id=user_id, rolle=role, flag=berechtigung_service.FLAG_SELBST_UEBERNEHMEN
        )
    if role != "custom":
        return True
    if account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.darf_vorgaenge_selbst_uebernehmen


async def darf_zeiten_buchen(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None, user_id: UUID | None = None
) -> bool:
    """Einzelrecht "Zeiten buchen" (docs/konzepte/ZEITERFASSUNG.md,
    Abschnitt 5.4) -- steuert den gesamten Buchungsablauf in
    app/api/routes/zeiterfassung.py (vormerken/buchen/stornieren, fremde
    Eintraege bearbeiten, fremden Timer beenden). mandant_admin/super_admin
    duerfen immer buchen; fuer role='custom' ist es ein Schalter je
    Account-Typ (AccountTyp.darf_zeiten_buchen), unabhaengig von Rolle oder
    Geraet -- auch ein Techniker in der Feld-App kann es haben. Gleiches
    Muster wie darf_vorgang_selbst_uebernehmen oben."""
    if user_id is not None:
        return await berechtigung_service.flag_von(
            session, user_id=user_id, rolle=role, flag=berechtigung_service.FLAG_ZEITEN_BUCHEN
        )
    if role != "custom":
        return True
    if account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.darf_zeiten_buchen


async def darf_abwesenheiten_verwalten(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None, user_id: UUID | None = None
) -> bool:
    """Einzelrecht "Abwesenheiten verwalten" -- Soll-Arbeitszeit, Feiertage und
    Bundesland pflegen sowie fremdes Soll/Saldo lesen (app/api/routes/
    arbeitszeit.py). Gleiches Muster wie darf_zeiten_buchen: Nicht-custom-
    Rollen duerfen immer, custom nur per Schalter am Account-Typ."""
    if user_id is not None:
        return await berechtigung_service.flag_von(
            session, user_id=user_id, rolle=role, flag=berechtigung_service.FLAG_ABWESENHEITEN_VERWALTEN
        )
    if role != "custom":
        return True
    if account_typ_id is None:
        return False
    account_typ = await session.get(AccountTyp, account_typ_id)
    return account_typ is not None and account_typ.darf_abwesenheiten_verwalten


async def darf_fremde_mitarbeiterdaten_einsehen(
    session: AsyncSession, *, role: str, account_typ_id: UUID | None, user_id: UUID | None = None
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
        session,
        account_typ_id=account_typ_id,
        user_id=user_id,
        role=role,
        bereich="mitarbeiterverwaltung",
        aktion="bearbeiten",
    )


async def hat_recht(
    session: AsyncSession,
    *,
    account_typ_id: UUID | None,
    bereich: str,
    aktion: str,
    user_id: UUID | None = None,
    role: str = "custom",
) -> bool:
    """Mit user_id: Engine (role != custom hat alle Rechte). Ohne: nur die Matrix
    des Account-Typs."""
    if user_id is not None:
        rechte = await berechtigung_service.effektive_rechte_gecacht(session, user_id=user_id, rolle=role)
        return rechte.hat(bereich, aktion)
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
        bereich: {aktion: False for aktion in aktionen_fuer_bereich(bereich)} for bereich in RECHTE_BEREICHE
    }
    result = await session.execute(
        select(AccountTypRecht).where(AccountTypRecht.account_typ_id == account_typ_id)
    )
    for row in result.scalars().all():
        matrix.setdefault(row.bereich, {})[row.aktion] = row.erlaubt
    return matrix
