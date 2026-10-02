"""Aenderungsantraege zum Zeitplan: Techniker ohne projekte.bearbeiten melden
Verschiebungen/Dauer-Aenderungen/Probleme, das Office entscheidet. Die Annahme
laeuft ueber zeitplan_service.element_aendern -- dadurch gelten Propagation
(Projektmodus), gesperrte Liefertermine und Phasenspannen unveraendert."""
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.auftrag import Auftrag
from app.models.notification import Notification
from app.models.projekt import Projekt, ProjektAufgabe
from app.models.termin import Termin
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.zeitplan_antrag import ZeitplanAenderungsantrag
from app.schemas.zeitplan_antrag import ZeitplanAntragCreate, ZeitplanAntragRead, ZeitplanMeinRead
from app.services import zeitplan_service as zp
from app.services.event_bus import event_bus
from app.services.zuweisung_service import (
    assigned_kunde_ids,
    dispo_verantwortliche_user_ids,
    projekt_bearbeiter_user_ids,
)


class AntragKonflikt(zp.ZeitplanFehler):
    """Doppelter Antrag bzw. Antrag nicht mehr bearbeitbar -> 409."""


class AntragNichtErlaubt(zp.ZeitplanFehler):
    """Fremder Antrag -> 403."""


async def _element(session: AsyncSession, projekt_id: UUID, element_id: UUID) -> ProjektAufgabe:
    el = (
        await session.execute(
            select(ProjektAufgabe).where(
                ProjektAufgabe.id == element_id,
                ProjektAufgabe.projekt_id == projekt_id,
                ProjektAufgabe.typ.in_(zp.ZEITPLAN_TYPEN),
                ProjektAufgabe.geloescht_am.is_(None),
            )
        )
    ).scalar_one_or_none()
    if el is None:
        raise zp.ZeitplanNichtGefunden("Element nicht gefunden")
    return el


async def erstellen(
    session: AsyncSession, projekt: Projekt, *, mandant_id: UUID, user: User, body: ZeitplanAntragCreate
) -> ZeitplanAenderungsantrag:
    el = await _element(session, projekt.id, body.element_id)
    if el.typ == "phase":
        raise zp.ZeitplanRegelverstoss("Änderungen können nur für Schritte und Meilensteine beantragt werden")
    start, ende = body.gewuenschter_start_am, body.gewuenschtes_ende_am

    if body.art == "problem":
        if start is not None or ende is not None:
            raise zp.ZeitplanRegelverstoss("Eine Problemmeldung enthält keine Wunschtermine")
    else:
        if await zp._aktive_bestellung(session, el.bestellung_id) is not None:
            raise zp.ZeitplanRegelverstoss(
                "Das Datum kommt aus der Bestellung (Liefertermin) -- bitte ein Problem melden"
            )
        if body.art == "verschieben":
            if start is None:
                raise zp.ZeitplanRegelverstoss("Für eine Verschiebung wird ein Wunsch-Start benötigt")
            if ende is None:
                dauer = (el.ende_am - el.start_am) if el.start_am and el.ende_am else timedelta(0)
                ende = start + dauer
            if el.typ == "meilenstein":
                ende = start
            if ende < start:
                raise zp.ZeitplanRegelverstoss("Ende liegt vor dem Start")
        else:  # dauer_aendern
            if el.typ == "meilenstein":
                raise zp.ZeitplanRegelverstoss("Die Dauer eines Meilensteins kann nicht geändert werden")
            if ende is None:
                raise zp.ZeitplanRegelverstoss("Für eine Dauer-Änderung wird ein Wunsch-Ende benötigt")
            start = None
            if el.start_am is not None and ende < el.start_am:
                raise zp.ZeitplanRegelverstoss("Ende liegt vor dem Start")

    vorhanden = (
        await session.execute(
            select(ZeitplanAenderungsantrag.id).where(
                ZeitplanAenderungsantrag.element_id == el.id,
                ZeitplanAenderungsantrag.erstellt_von == user.id,
                ZeitplanAenderungsantrag.status == "offen",
            )
        )
    ).first()
    if vorhanden is not None:
        raise AntragKonflikt("Für diesen Schritt liegt von dir bereits ein offener Antrag vor")

    antrag = ZeitplanAenderungsantrag(
        mandant_id=mandant_id,
        projekt_id=projekt.id,
        element_id=el.id,
        art=body.art,
        gewuenschter_start_am=start,
        gewuenschtes_ende_am=ende,
        begruendung=body.begruendung,
        erstellt_von=user.id,
    )
    session.add(antrag)
    await session.flush()
    await session.refresh(antrag)

    # Empfaenger: Zustaendiger des Elements (nur wenn Office-Nutzer) + Projekt-
    # Ersteller; ohne beide die Dispo-Verantwortlichen (wie Partner-Kommentar).
    bearbeiter = await projekt_bearbeiter_user_ids(session, mandant_id)
    empfaenger: set[UUID] = set()
    if el.zugewiesen_an in bearbeiter:
        empfaenger.add(el.zugewiesen_an)
    if projekt.erstellt_von in bearbeiter:
        empfaenger.add(projekt.erstellt_von)
    if not empfaenger:
        empfaenger = await dispo_verantwortliche_user_ids(session, mandant_id)
    empfaenger.discard(user.id)
    await _benachrichtige(
        session,
        mandant_id,
        projekt,
        empfaenger,
        f"Änderungsantrag von {user.name} im Projekt {projekt.name}: {el.titel}",
    )
    return antrag


async def _benachrichtige(
    session: AsyncSession, mandant_id: UUID, projekt: Projekt, user_ids: set[UUID], titel: str
) -> None:
    if not user_ids:
        return
    for uid in user_ids:
        session.add(
            Notification(
                mandant_id=mandant_id,
                user_id=uid,
                typ="zeitplan_antrag",
                titel=titel,
                ref_entity_type="projekt",
                ref_entity_id=projekt.id,
            )
        )
    await session.flush()
    await event_bus.publish(
        mandant_id, "notification", {"typ": "zeitplan_antrag", "projekt_id": str(projekt.id)}
    )


async def lesen(
    session: AsyncSession,
    projekt_id: UUID,
    *,
    nur_von: UUID | None = None,
    status: str | None = None,
    antrag_id: UUID | None = None,
) -> list[ZeitplanAntragRead]:
    ersteller, bearbeiter = aliased(User), aliased(User)
    stmt = (
        select(ZeitplanAenderungsantrag, ProjektAufgabe, ersteller.name, bearbeiter.name)
        .join(ProjektAufgabe, ProjektAufgabe.id == ZeitplanAenderungsantrag.element_id)
        .outerjoin(ersteller, ersteller.id == ZeitplanAenderungsantrag.erstellt_von)
        .outerjoin(bearbeiter, bearbeiter.id == ZeitplanAenderungsantrag.bearbeitet_von)
        .where(ZeitplanAenderungsantrag.projekt_id == projekt_id)
        .order_by(ZeitplanAenderungsantrag.erstellt_am.desc(), ZeitplanAenderungsantrag.id)
    )
    if nur_von is not None:
        stmt = stmt.where(ZeitplanAenderungsantrag.erstellt_von == nur_von)
    if status is not None:
        stmt = stmt.where(ZeitplanAenderungsantrag.status == status)
    if antrag_id is not None:
        stmt = stmt.where(ZeitplanAenderungsantrag.id == antrag_id)
    return [
        ZeitplanAntragRead(
            id=a.id,
            element_id=a.element_id,
            element_titel=el.titel,
            art=a.art,  # type: ignore[arg-type]
            gewuenschter_start_am=a.gewuenschter_start_am,
            gewuenschtes_ende_am=a.gewuenschtes_ende_am,
            aktueller_start_am=el.start_am,
            aktuelles_ende_am=el.ende_am,
            begruendung=a.begruendung,
            status=a.status,  # type: ignore[arg-type]
            antwort=a.antwort,
            erstellt_von=a.erstellt_von,
            erstellt_von_name=e_name,
            erstellt_am=a.erstellt_am,
            bearbeitet_von_name=b_name,
            bearbeitet_am=a.bearbeitet_am,
        )
        for a, el, e_name, b_name in (await session.execute(stmt)).all()
    ]


async def lese_einen(session: AsyncSession, projekt_id: UUID, antrag_id: UUID) -> ZeitplanAntragRead:
    return (await lesen(session, projekt_id, antrag_id=antrag_id))[0]


async def _offener_antrag(session: AsyncSession, projekt_id: UUID, antrag_id: UUID) -> ZeitplanAenderungsantrag:
    antrag = (
        await session.execute(
            select(ZeitplanAenderungsantrag).where(
                ZeitplanAenderungsantrag.id == antrag_id, ZeitplanAenderungsantrag.projekt_id == projekt_id
            )
        )
    ).scalar_one_or_none()
    if antrag is None:
        raise zp.ZeitplanNichtGefunden("Antrag nicht gefunden")
    if antrag.status != "offen":
        raise AntragKonflikt("Der Antrag wurde bereits bearbeitet")
    return antrag


def _abschliessen(antrag: ZeitplanAenderungsantrag, status: str, user_id: UUID, antwort: str | None) -> None:
    antrag.status = status
    antrag.antwort = antwort
    antrag.bearbeitet_von = user_id
    antrag.bearbeitet_am = datetime.now(UTC)


async def annehmen(
    session: AsyncSession,
    projekt: Projekt,
    antrag_id: UUID,
    *,
    user: User,
    antwort: str | None,
    erlaubte_kunden: set[UUID] | None,
) -> None:
    antrag = await _offener_antrag(session, projekt.id, antrag_id)
    try:
        el = await _element(session, projekt.id, antrag.element_id)
    except zp.ZeitplanNichtGefunden as exc:
        raise AntragKonflikt("Der Schritt wurde inzwischen gelöscht") from exc
    if antrag.art == "verschieben":
        await zp.element_aendern(
            session,
            projekt,
            el.id,
            {"start_am": antrag.gewuenschter_start_am, "ende_am": antrag.gewuenschtes_ende_am},
            antrag.mandant_id,
            erlaubte_kunden,
        )
    elif antrag.art == "dauer_aendern":
        await zp.element_aendern(
            session, projekt, el.id, {"ende_am": antrag.gewuenschtes_ende_am}, antrag.mandant_id, erlaubte_kunden
        )
    _abschliessen(antrag, "angenommen", user.id, antwort)
    await session.flush()
    await _melde_entscheidung(session, projekt, antrag, el.titel, "angenommen")


async def ablehnen(session: AsyncSession, projekt: Projekt, antrag_id: UUID, *, user: User, antwort: str) -> None:
    antrag = await _offener_antrag(session, projekt.id, antrag_id)
    el = await session.get(ProjektAufgabe, antrag.element_id)
    _abschliessen(antrag, "abgelehnt", user.id, antwort)
    await session.flush()
    await _melde_entscheidung(session, projekt, antrag, el.titel if el else "Schritt", "abgelehnt")


async def zurueckziehen(session: AsyncSession, projekt: Projekt, antrag_id: UUID, *, user: User) -> None:
    antrag = await _offener_antrag(session, projekt.id, antrag_id)
    if antrag.erstellt_von != user.id:
        raise AntragNichtErlaubt("Nur der Antragsteller kann den Antrag zurückziehen")
    # bearbeitet_* bleibt leer: es hat kein Office-Nutzer entschieden.
    antrag.status = "zurueckgezogen"
    await session.flush()


async def _melde_entscheidung(
    session: AsyncSession, projekt: Projekt, antrag: ZeitplanAenderungsantrag, titel: str, ergebnis: str
) -> None:
    empfaenger = {antrag.erstellt_von}
    empfaenger.discard(antrag.bearbeitet_von)
    await _benachrichtige(
        session,
        antrag.mandant_id,
        projekt,
        empfaenger,
        f"Dein Änderungsantrag zu „{titel}“ ({projekt.name}) wurde {ergebnis}",
    )


async def _mitarbeit_bedingung(session: AsyncSession, user_id: UUID):
    """Eine einzige Definition von "arbeitet im Projekt mit" (Bezug: Projekt):
    Zustaendiger eines Elements, zugewiesener Techniker/Termin eines
    verknuepften Vorgangs oder ein dem Nutzer zugewiesener Kunde am Projekt
    (Auftrag, Vorgang oder Vertrag)."""
    kunden = await assigned_kunde_ids(session, user_id)
    pa = ProjektAufgabe
    mitarbeit = [
        exists().where(
            pa.projekt_id == Projekt.id,
            pa.typ.in_(zp.ZEITPLAN_TYPEN),
            pa.geloescht_am.is_(None),
            pa.zugewiesen_an == user_id,
        ),
        exists()
        .where(pa.projekt_id == Projekt.id, pa.geloescht_am.is_(None), pa.typ.in_(zp.ZEITPLAN_TYPEN))
        .where(
            exists().where(
                Vorgang.id == pa.vorgang_id,
                Vorgang.geloescht_am.is_(None),
                or_(
                    Vorgang.zugewiesener_user_id == user_id,
                    exists().where(
                        Termin.vorgang_id == Vorgang.id,
                        Termin.techniker_id == user_id,
                        Termin.geloescht_am.is_(None),
                    ),
                ),
            )
        ),
    ]
    if kunden:
        mitarbeit += [
            exists().where(
                Auftrag.projekt_id == Projekt.id, Auftrag.geloescht_am.is_(None), Auftrag.kunde_id.in_(kunden)
            ),
            exists().where(
                Vorgang.projekt_id == Projekt.id, Vorgang.geloescht_am.is_(None), Vorgang.kunde_id.in_(kunden)
            ),
            exists().where(and_(Vertrag.id == Projekt.vertrag_id, Vertrag.kunde_id.in_(kunden))),
        ]
    return or_(*mitarbeit)


async def hat_mitarbeit(session: AsyncSession, user_id: UUID, projekt_id: UUID) -> bool:
    """Gleiche Definition wie meine_zeitplaene (Feld-App-Liste)."""
    stmt = select(Projekt.id).where(
        Projekt.id == projekt_id,
        Projekt.geloescht_am.is_(None),
        await _mitarbeit_bedingung(session, user_id),
    )
    return (await session.execute(stmt)).first() is not None


async def meine_zeitplaene(
    session: AsyncSession, user_id: UUID, *, alle: bool, heute: date
) -> list[ZeitplanMeinRead]:
    """Projekte fuer die Feld-App-Liste. alle=False (nur zeitplan_sehen): nur
    Projekte mit Mitarbeit (siehe _mitarbeit_bedingung)."""
    stmt = select(Projekt.id, Projekt.name).where(Projekt.geloescht_am.is_(None), Projekt.archiviert.is_(False))
    if not alle:
        stmt = stmt.where(await _mitarbeit_bedingung(session, user_id))
    projekte = (await session.execute(stmt.order_by(Projekt.name))).all()
    if not projekte:
        return []

    naechste: dict[UUID, tuple[str, date]] = {}
    for pid, titel, start in (
        await session.execute(
            select(ProjektAufgabe.projekt_id, ProjektAufgabe.titel, ProjektAufgabe.start_am)
            .where(
                ProjektAufgabe.projekt_id.in_([p[0] for p in projekte]),
                ProjektAufgabe.typ.in_(("schritt", "meilenstein")),
                ProjektAufgabe.geloescht_am.is_(None),
                ProjektAufgabe.erledigt_am.is_(None),
                ProjektAufgabe.start_am.is_not(None),
                ProjektAufgabe.ende_am >= heute,
            )
            .order_by(ProjektAufgabe.start_am, ProjektAufgabe.plan_reihenfolge)
        )
    ).all():
        naechste.setdefault(pid, (titel, start))
    return [
        ZeitplanMeinRead(
            id=pid,
            name=name,
            naechster_schritt_titel=naechste[pid][0] if pid in naechste else None,
            naechster_schritt_start=naechste[pid][1] if pid in naechste else None,
        )
        for pid, name in projekte
    ]
