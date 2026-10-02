from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.user_anonymisierung_service import nicht_anonymisiert

if TYPE_CHECKING:
    from app.api.deps import AuthContext

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


async def erlaubte_kunde_ids(session: AsyncSession, auth: "AuthContext") -> set[UUID] | None:
    """None = keine Einschraenkung, sonst die Menge der zugewiesenen Kunden.
    Gemeinsamer Einstieg fuer Listen/Aggregationen, die nach
    kunde_id.in_(...) filtern (Muster wie kunden.py/vorgaenge.py)."""
    if not await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        return None
    return await assigned_kunde_ids(session, auth.user_id)


async def require_kunde_zugriff(
    session: AsyncSession, auth: "AuthContext", kunde_id: UUID | None, detail: str
) -> None:
    """404 statt 403, damit die Existenz fremder Datensaetze nicht verraten
    wird (wie _require_kunde_zugriff in kunden.py). kunde_id=None (Datensatz
    ohne Kunde) bleibt fuer Eingeschraenkte unsichtbar."""
    erlaubt = await erlaubte_kunde_ids(session, auth)
    if erlaubt is not None and (kunde_id is None or kunde_id not in erlaubt):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


async def require_kunde_zugewiesen(
    session: AsyncSession, auth: "AuthContext", kunde_id: UUID
) -> None:
    """Schreibzugriff beim Anlegen: 403 wie in vorgaenge.py (der Kunde ist dem
    Nutzer bekannt, er darf nur nichts dafuer erfassen)."""
    erlaubt = await erlaubte_kunde_ids(session, auth)
    if erlaubt is not None and kunde_id not in erlaubt:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dieser Kunde ist dir nicht zugewiesen"
        )


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


async def zuweisbare_user_ids(session: AsyncSession, user_ids: set[UUID]) -> set[UUID]:
    """Teilmenge der user_ids, die neu zugewiesen werden duerfen: aktiv und
    nicht anonymisiert (deaktivierte/geloeschte Nutzer erhalten keine neuen
    Kunden/Vorgaenge/Fahrzeuge; bestehende Zuweisungen bleiben als Historie)."""
    if not user_ids:
        return set()
    result = await session.execute(
        select(User.id).where(User.id.in_(user_ids), User.aktiv.is_(True), nicht_anonymisiert())
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
