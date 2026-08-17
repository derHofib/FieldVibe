from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User

# Nutzer mit einem Account-Typ, dessen nur_zugewiesene_kunden-Schalter aktiv
# ist (ehemals fest an die Rolle "techniker" gebunden), sehen -- anders als
# mandant_admin/disponent-artige Account-Typen -- nur Kunden, denen sie
# explizit zugewiesen sind (siehe kunden.py/anlagen.py/vorgaenge.py/
# feed.py/search.py). Diese Einschraenkung ist eine fachliche Sichtbarkeits-
# regel, keine Mandanten-Isolation, und laeuft daher bewusst auf
# Anwendungsebene statt per RLS -- RLS bleibt fuer die haerte
# Mandantengrenze reserviert.


async def assigned_kunde_ids(session: AsyncSession, user_id: UUID) -> set[UUID]:
    result = await session.execute(
        select(KundeZuweisung.kunde_id).where(KundeZuweisung.user_id == user_id)
    )
    return set(result.scalars().all())


async def technik_user_ids(session: AsyncSession, mandant_id: UUID | None) -> set[UUID]:
    """Ersetzt das fruehere User.role == 'techniker' fuer
    Zuweisungs-Dropdowns: alle Nutzer, deren Account-Typ auf zugewiesene
    Kunden beschraenkt ist."""
    result = await session.execute(
        select(User.id)
        .join(AccountTyp, AccountTyp.id == User.account_typ_id)
        .where(
            User.role == "custom",
            User.mandant_id == mandant_id,
            AccountTyp.nur_zugewiesene_kunden.is_(True),
        )
    )
    return set(result.scalars().all())


async def _verantwortliche_user_ids(
    session: AsyncSession, mandant_id: UUID, *, bereich: str, aktion: str = "bearbeiten"
) -> set[UUID]:
    result = await session.execute(
        select(User.id)
        .outerjoin(AccountTyp, AccountTyp.id == User.account_typ_id)
        .outerjoin(
            AccountTypRecht,
            (AccountTypRecht.account_typ_id == AccountTyp.id)
            & (AccountTypRecht.bereich == bereich)
            & (AccountTypRecht.aktion == aktion),
        )
        .where(
            User.mandant_id == mandant_id,
            User.aktiv.is_(True),
            or_(User.role == "mandant_admin", AccountTypRecht.erlaubt.is_(True)),
        )
    )
    return set(result.scalars().all())


async def dispo_verantwortliche_user_ids(session: AsyncSession, mandant_id: UUID) -> set[UUID]:
    """Ersetzt das fruehere User.role.in_(("mandant_admin", "disponent")) fuer
    dispositionsbezogene Benachrichtigungs-Empfaenger (z.B. neue Kundenportal-
    Auftragsanfragen, faellige Pruefzyklen/Dauerauftraege): mandant_admin
    immer, dazu Nutzer mit einem Account-Typ, dessen Rechte-Matrix
    dispo.bearbeiten erlaubt (die disponent-aequivalente Berechtigung)."""
    return await _verantwortliche_user_ids(session, mandant_id, bereich="dispo")


async def abrechnung_verantwortliche_user_ids(session: AsyncSession, mandant_id: UUID) -> set[UUID]:
    """Wie dispo_verantwortliche_user_ids, aber fuer abrechnungsbezogene
    Benachrichtigungen (z.B. Mahnwesen-Eskalationen): gate ueber
    abrechnung.bearbeiten statt dispo.bearbeiten."""
    return await _verantwortliche_user_ids(session, mandant_id, bereich="abrechnung")
