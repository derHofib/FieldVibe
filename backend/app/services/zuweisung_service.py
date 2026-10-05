from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User
from app.services import berechtigung_service
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


_SCOPE_CACHE_KEY = "zuweisung_scope_cache"


async def _scope_cache(session: AsyncSession, auth: "AuthContext") -> dict:
    """Mengen pro Request cachen. Der Cache haengt am Engine-Cache: wird der
    (berechtigung_service.cache_leeren) verworfen, ist auch dieser ungueltig."""
    await berechtigung_service.effektive_rechte_gecacht(
        session, user_id=auth.user_id, rolle=auth.role
    )
    engine_cache = session.info.get(berechtigung_service._CACHE_KEY)
    gespeichert = session.info.get(_SCOPE_CACHE_KEY)
    if gespeichert is None or gespeichert[0] is not engine_cache:
        gespeichert = (engine_cache, {})
        session.info[_SCOPE_CACHE_KEY] = gespeichert
    return gespeichert[1]


def scope_cache_leeren(session: AsyncSession) -> None:
    """Nach Aenderungen an Kundenzuweisungen/Besetzungen im selben Request."""
    session.info.pop(_SCOPE_CACHE_KEY, None)


async def erlaubte_user_ids(
    session: AsyncSession, auth: "AuthContext", bereich: str, aktion: str = "sehen"
) -> set[UUID] | None:
    """None = keine Einschraenkung (Scope mandant), sonst die Nutzer, deren
    Daten (zugewiesener_user_id/techniker_id/zugewiesen_an) im Scope liegen.
    Fehlt das Recht, bleibt nur der Nutzer selbst."""
    cache = await _scope_cache(session, auth)
    key = ("user", auth.user_id, bereich, aktion)
    if key not in cache:
        ids = await berechtigung_service.user_ids_fuer_recht(session, auth, bereich, aktion)
        cache[key] = ids if ids is None else ids | {auth.user_id}
    return cache[key]


async def erlaubte_kunde_ids(
    session: AsyncSession, auth: "AuthContext", aktion: str = "sehen"
) -> set[UUID] | None:
    """None = keine Einschraenkung, sonst die Kunden, die einem Nutzer im Scope
    von kunden.<aktion> zugewiesen sind (Scope eigene = die eigenen
    Zuweisungen). Gemeinsamer Einstieg fuer Listen/Aggregationen, die nach
    kunde_id.in_(...) filtern.

    Ohne Recht fuer die Aktion gilt der Scope von kunden.sehen (der Routen-Gate
    liegt in require_recht); ohne jedes kunden-Recht bleibt es wie vor den
    Scopes unbeschraenkt, ausser das Altflag nur_zugewiesene_kunden greift
    (fail-safe, siehe berechtigung_service.ist_auf_zugewiesene_kunden_beschraenkt)."""
    cache = await _scope_cache(session, auth)
    key = ("kunde", auth.user_id, aktion)
    if key in cache:
        return cache[key]
    wirk_aktion = aktion
    scope = await berechtigung_service.scope_von(session, auth, "kunden", aktion)
    if scope is None and aktion != "sehen":
        wirk_aktion = "sehen"
        scope = await berechtigung_service.scope_von(session, auth, "kunden", "sehen")
    if scope is None or scope == "mandant":
        fallback_flag = await ist_auf_zugewiesene_kunden_beschraenkt(
            session, role=auth.role, account_typ_id=auth.account_typ_id, user_id=auth.user_id
        )
        user_ids: set[UUID] | None = {auth.user_id} if fallback_flag else None
    else:
        user_ids = await erlaubte_user_ids(session, auth, "kunden", wirk_aktion)
    if user_ids is None:
        ergebnis = None
    elif user_ids == {auth.user_id}:
        ergebnis = await assigned_kunde_ids(session, auth.user_id)
    else:
        zeilen = await session.execute(
            select(KundeZuweisung.kunde_id).where(KundeZuweisung.user_id.in_(user_ids))
        )
        ergebnis = set(zeilen.scalars().all())
    cache[key] = ergebnis
    return ergebnis


async def vorgang_scope_filter(
    session: AsyncSession, auth: "AuthContext", aktion: str = "sehen"
):
    """WHERE-Klausel fuer Vorgang-Abfragen (None = unbeschraenkt): Vorgang des
    Kunden im Kunden-Scope ODER dem Nutzer im Scope von vorgaenge.<aktion>
    zugewiesen. Bei Scope mandant fuer Vorgaenge keine Einschraenkung; ist der
    Vorgaenge-Scope enger als der Kunden-Scope (z.B. kunden=mandant), zaehlt
    nur die Zuweisung."""
    from app.models.vorgang import Vorgang

    v_scope = await berechtigung_service.scope_von(session, auth, "vorgaenge", aktion)
    kunden = await erlaubte_kunde_ids(session, auth, "sehen")
    if v_scope == "mandant":
        return None
    if v_scope is None:
        # Kein vorgaenge-Recht (Gate liegt an der Route): wie bisher nur Kundenlogik.
        return None if kunden is None else Vorgang.kunde_id.in_(kunden)
    users = await erlaubte_user_ids(session, auth, "vorgaenge", aktion)
    bedingungen = [Vorgang.zugewiesener_user_id.in_(users)]
    if kunden is not None:
        bedingungen.append(Vorgang.kunde_id.in_(kunden))
    return or_(*bedingungen)


async def require_vorgang_zugriff(
    session: AsyncSession, auth: "AuthContext", vorgang, aktion: str = "sehen"
) -> None:
    """404 statt 403 wie require_kunde_zugriff."""
    klausel = await vorgang_scope_filter(session, auth, aktion)
    if klausel is None:
        return
    from app.models.vorgang import Vorgang

    treffer = await session.execute(
        select(Vorgang.id).where(Vorgang.id == vorgang.id, klausel)
    )
    if treffer.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")


async def require_user_scope(
    session: AsyncSession,
    auth: "AuthContext",
    bereich: str,
    aktion: str,
    user_id: UUID | None,
    detail: str,
) -> None:
    """404, wenn die zustaendige Person (techniker_id/zugewiesen_an) ausserhalb
    des Scopes liegt; user_id=None (niemand zustaendig) ist nur bei Scope
    mandant erreichbar."""
    erlaubt = await erlaubte_user_ids(session, auth, bereich, aktion)
    if erlaubt is not None and (user_id is None or user_id not in erlaubt):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


async def require_kunde_zugriff(
    session: AsyncSession,
    auth: "AuthContext",
    kunde_id: UUID | None,
    detail: str,
    aktion: str = "sehen",
) -> None:
    """404 statt 403, damit die Existenz fremder Datensaetze nicht verraten
    wird (wie _require_kunde_zugriff in kunden.py). kunde_id=None (Datensatz
    ohne Kunde) bleibt fuer Eingeschraenkte unsichtbar."""
    erlaubt = await erlaubte_kunde_ids(session, auth, aktion)
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


async def projekt_bearbeiter_user_ids(session: AsyncSession, mandant_id: UUID) -> set[UUID]:
    """Aktive Nutzer mit Schreibrecht auf Projekte (mandant_admin immer) --
    Empfaenger fuer Zeitplan-Aenderungsantraege und Filter fuer "Office-Nutzer"."""
    return await _verantwortliche_user_ids(session, mandant_id, bereich="projekte")


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


async def darf_mitarbeiterdaten_einsehen(
    session: AsyncSession, auth: "AuthContext", ziel_user_id: UUID, aktion: str = "bearbeiten"
) -> bool:
    """Scope-Variante von rechte_service.darf_fremde_mitarbeiterdaten_einsehen:
    eigene Daten immer, fremde nur fuer Nutzer im Scope von
    mitarbeiterverwaltung.<aktion> (Aktion "bearbeiten" wie der bisherige Gate)."""
    if ziel_user_id == auth.user_id:
        return True
    erlaubt = await erlaubte_user_ids(session, auth, "mitarbeiterverwaltung", aktion)
    return erlaubt is None or ziel_user_id in erlaubt
