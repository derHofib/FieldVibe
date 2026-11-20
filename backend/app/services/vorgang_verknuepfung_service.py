"""Kette Projekt > Auftrag > Vorgang (Konzept auftrag-projekt): Regeln beim
Zuordnen, Anreicherung der Antworten mit Namen und serverseitige Ausblendung
fuer eigenstaendig gefuehrte Vorgaenge."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auftrag import Auftrag
from app.models.leistungsverzeichnis import LeistungsverzeichnisVerwendung
from app.models.mangel import Mangel
from app.models.material import MaterialVerwendung
from app.models.material_bedarf import MaterialBedarf
from app.models.projekt import Projekt
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.vorgang import VorgangRead
from app.schemas.vorgang_verknuepfung import (
    HerkunftSchritt,
    Rueckmeldung,
    VerknuepfungAuftrag,
    VerknuepfungGeschwister,
    VerknuepfungProjekt,
    VorgangVerknuepfung,
)
from app.services import berechtigung_service
from app.services.vor_ort_kontakt_service import hauptkontakte_fuer_vorgaenge
from app.services.zuweisung_service import vorgang_scope_filter

BEREICH = "vorgaenge"
AKTION = "eigenstaendig_setzen"
# Ereignisse, die Projekt-/Auftragsnamen oder die Eigenstaendigkeit verraten.
VERKNUEPFUNG_EVENT_TYPEN = ("zuordnung_geaendert", "eigenstaendig_gesetzt", "eigenstaendig_aufgehoben")
_MAX_ELTERN_TIEFE = 20


async def hat_eigenstaendig_recht(session: AsyncSession, auth) -> bool:
    return await berechtigung_service.hat_recht(session, auth, BEREICH, AKTION)


# --- Regel "eine Kette" ------------------------------------------------------


async def kette_aufloesen(
    session: AsyncSession,
    *,
    aktuell_projekt_id: UUID | None,
    aktuell_auftrag_id: UUID | None,
    aendert_auftrag: bool,
    neu_auftrag_id: UUID | None,
    aendert_projekt: bool,
    neu_projekt_id: UUID | None,
) -> tuple[UUID | None, UUID | None]:
    """Liefert (projekt_id, auftrag_id) nach Regel 1: hat der Vorgang einen
    Auftrag, ist sein Projekt das des Auftrags. Ein davon abweichendes,
    gleichzeitig gesendetes projekt_id (oder ein Projektwechsel bei bleibendem
    Auftrag) ist ein 400. Wird nur der Auftrag entfernt, bleibt das bisherige
    Projekt als direkte Zuordnung ("Ohne Auftrag") erhalten."""
    auftrag_id = neu_auftrag_id if aendert_auftrag else aktuell_auftrag_id
    projekt_id = neu_projekt_id if aendert_projekt else aktuell_projekt_id
    if auftrag_id is None:
        return projekt_id, None
    auftrag = await session.get(Auftrag, auftrag_id)
    if auftrag is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auftrag nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if aendert_projekt and neu_projekt_id != auftrag.projekt_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Projekt passt nicht zum Auftrag")
    return auftrag.projekt_id, auftrag_id


async def _projekt_und_auftrag_namen(
    session: AsyncSession, projekt_id: UUID | None, auftrag_id: UUID | None
) -> dict:
    projekt = await session.get(Projekt, projekt_id) if projekt_id else None
    auftrag = await session.get(Auftrag, auftrag_id) if auftrag_id else None
    return {
        "projekt_id": str(projekt_id) if projekt_id else None,
        "auftrag_id": str(auftrag_id) if auftrag_id else None,
        "projekt_name": projekt.name if projekt else None,
        "auftrag_titel": auftrag.titel if auftrag else None,
    }


def _zuordnung_text(daten: dict) -> str:
    teile = [t for t in (daten["projekt_name"], daten["auftrag_titel"]) if t]
    return " › ".join(teile) if teile else "keine Zuordnung"


async def zuordnung_ereignis(
    session: AsyncSession,
    vorgang: Vorgang,
    *,
    alt: tuple[UUID | None, UUID | None],
    neu: tuple[UUID | None, UUID | None],
    author_user_id: UUID | None,
) -> None:
    """Schreibt zuordnung_geaendert, falls sich (projekt_id, auftrag_id) geaendert hat."""
    if alt == neu:
        return
    alt_daten = await _projekt_und_auftrag_namen(session, *alt)
    neu_daten = await _projekt_und_auftrag_namen(session, *neu)
    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=vorgang.id,
            event_type="zuordnung_geaendert",
            author_user_id=author_user_id,
            is_system=True,
            body=f"Zuordnung geändert: {_zuordnung_text(alt_daten)} → {_zuordnung_text(neu_daten)}",
            payload={"alt": alt_daten, "neu": neu_daten},
        )
    )


async def vorgaenge_des_auftrags_mitziehen(
    session: AsyncSession, auftrag: Auftrag, neues_projekt_id: UUID | None, *, author_user_id: UUID | None
) -> int:
    """Auftrag wechselt das Projekt: seine nicht-eigenstaendigen, nicht
    geloeschten Vorgaenge ziehen mit (auch abgeschlossene -- die Kette soll
    stimmen). Je Vorgang ein zuordnung_geaendert-Ereignis."""
    result = await session.execute(
        select(Vorgang).where(
            Vorgang.auftrag_id == auftrag.id,
            Vorgang.geloescht_am.is_(None),
            Vorgang.verknuepfung_eigenstaendig.is_(False),
            Vorgang.projekt_id.is_distinct_from(neues_projekt_id),
        )
    )
    vorgaenge = list(result.scalars().all())
    for vorgang in vorgaenge:
        alt = (vorgang.projekt_id, vorgang.auftrag_id)
        vorgang.projekt_id = neues_projekt_id
        await zuordnung_ereignis(
            session, vorgang, alt=alt, neu=(neues_projekt_id, vorgang.auftrag_id), author_user_id=author_user_id
        )
    return len(vorgaenge)


# --- Anreicherung + Ausblendung ---------------------------------------------


async def als_read(session: AsyncSession, auth, vorgaenge: list[Vorgang]) -> list[VorgangRead]:
    """ORM-Vorgaenge -> VorgangRead mit projekt_name/auftrag_titel/Eigenstaendig-
    Feldern, im Batch (je eine Abfrage fuer Projekte, Auftraege, Nutzernamen,
    Scope). Die Ausblendung passiert nur im Read-Objekt, nie am ORM-Objekt
    (sonst wuerde der naechste Flush sie in die DB schreiben)."""
    if not vorgaenge:
        return []
    hat_recht = await hat_eigenstaendig_recht(session, auth)

    projekt_ids = {v.projekt_id for v in vorgaenge if v.projekt_id}
    auftrag_ids = {v.auftrag_id for v in vorgaenge if v.auftrag_id}
    projekt_namen: dict[UUID, str] = {}
    if projekt_ids:
        zeilen = await session.execute(select(Projekt.id, Projekt.name).where(Projekt.id.in_(projekt_ids)))
        projekt_namen = {z[0]: z[1] for z in zeilen}
    auftrag_titel: dict[UUID, str] = {}
    if auftrag_ids:
        zeilen = await session.execute(select(Auftrag.id, Auftrag.titel).where(Auftrag.id.in_(auftrag_ids)))
        auftrag_titel = {z[0]: z[1] for z in zeilen}

    user_namen: dict[UUID, str] = {}
    von_ids = {v.verknuepfung_eigenstaendig_von for v in vorgaenge if v.verknuepfung_eigenstaendig_von}
    if hat_recht and von_ids:
        zeilen = await session.execute(select(User.id, User.name).where(User.id.in_(von_ids)))
        user_namen = {z[0]: z[1] for z in zeilen}

    darf_ids: set[UUID] = set()
    if hat_recht:
        klausel = await vorgang_scope_filter(session, auth, AKTION)
        if klausel is None:
            darf_ids = {v.id for v in vorgaenge}
        else:
            zeilen = await session.execute(
                select(Vorgang.id).where(Vorgang.id.in_([v.id for v in vorgaenge]), klausel)
            )
            darf_ids = {z[0] for z in zeilen}

    # Ohne das Recht sieht der Nutzer bei eigenstaendig gefuehrten Vorgaengen weder Auftrag noch Projekt --
    # deren Kontakte vor Ort bleiben dann ebenfalls aussen vor.
    haupt = await hauptkontakte_fuer_vorgaenge(
        session,
        vorgaenge,
        ohne_vererbung=frozenset() if hat_recht else frozenset(v.id for v in vorgaenge if v.verknuepfung_eigenstaendig),
    )

    gelesen = []
    for vorgang in vorgaenge:
        read = VorgangRead.model_validate(vorgang)
        read.hauptkontakt_vor_ort = haupt.get(vorgang.id)
        if vorgang.verknuepfung_eigenstaendig and not hat_recht:
            read.projekt_id = None
            read.auftrag_id = None
            read.verknuepfung_eigenstaendig_am = None
        else:
            read.projekt_name = projekt_namen.get(vorgang.projekt_id) if vorgang.projekt_id else None
            read.auftrag_titel = auftrag_titel.get(vorgang.auftrag_id) if vorgang.auftrag_id else None
            if vorgang.verknuepfung_eigenstaendig_von:
                read.verknuepfung_eigenstaendig_von_name = user_namen.get(vorgang.verknuepfung_eigenstaendig_von)
        read.darf_eigenstaendig_setzen = vorgang.id in darf_ids
        gelesen.append(read)
    return gelesen


async def als_read_einzeln(session: AsyncSession, auth, vorgang: Vorgang) -> VorgangRead:
    [gelesen] = await als_read(session, auth, [vorgang])
    return gelesen


async def projekt_filter_sichtbarkeit(session: AsyncSession, auth):
    """Zusatzbedingung fuer Listen, die nach projekt_id/auftrag_id filtern:
    Nutzer ohne das Recht duerfen eigenstaendige Vorgaenge darueber nicht
    finden (sonst verriete der Filter die ausgeblendete Zuordnung). None = keine."""
    if await hat_eigenstaendig_recht(session, auth):
        return None
    return Vorgang.verknuepfung_eigenstaendig.is_(False)


# --- Eigenstaendig fuehren ---------------------------------------------------


async def eigenstaendig_setzen(
    session: AsyncSession, vorgang: Vorgang, eigenstaendig: bool, *, user_id: UUID
) -> bool:
    """True, wenn sich etwas geaendert hat (sonst idempotent ohne Ereignis)."""
    if vorgang.projekt_id is None and vorgang.auftrag_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang gehört weder zu einem Projekt noch zu einem Auftrag",
        )
    if vorgang.verknuepfung_eigenstaendig == eigenstaendig:
        return False
    vorgang.verknuepfung_eigenstaendig = eigenstaendig
    vorgang.verknuepfung_eigenstaendig_am = datetime.now(timezone.utc) if eigenstaendig else None
    vorgang.verknuepfung_eigenstaendig_von = user_id if eigenstaendig else None
    daten = await _projekt_und_auftrag_namen(session, vorgang.projekt_id, vorgang.auftrag_id)
    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=vorgang.id,
            event_type="eigenstaendig_gesetzt" if eigenstaendig else "eigenstaendig_aufgehoben",
            author_user_id=user_id,
            is_system=True,
            body="Eigenständig geführt" if eigenstaendig else "Eigenständige Führung aufgehoben",
            payload=daten,
        )
    )
    return True


# --- GET /vorgaenge/{id}/verknuepfung ---------------------------------------


async def _sichtbare_vorgaenge_stmt(session: AsyncSession, auth, hat_recht: bool, aktuell_id: UUID):
    """Basis-Abfrage fuer Vorgaenge im Sichtbereich des Nutzers (Scope; ohne
    Recht ohne eigenstaendige). Der aktuelle Vorgang bleibt immer enthalten."""
    stmt = select(Vorgang).where(Vorgang.geloescht_am.is_(None))
    klausel = await vorgang_scope_filter(session, auth)
    if klausel is not None:
        stmt = stmt.where(klausel)
    if not hat_recht:
        stmt = stmt.where(Vorgang.verknuepfung_eigenstaendig.is_(False) | (Vorgang.id == aktuell_id))
    return stmt


async def verknuepfung_lesen(session: AsyncSession, auth, vorgang: Vorgang) -> VorgangVerknuepfung:
    hat_recht = await hat_eigenstaendig_recht(session, auth)
    if (vorgang.projekt_id is None and vorgang.auftrag_id is None) or (
        vorgang.verknuepfung_eigenstaendig and not hat_recht
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine Verknüpfung vorhanden")

    projekt = await session.get(Projekt, vorgang.projekt_id) if vorgang.projekt_id else None
    auftrag = await session.get(Auftrag, vorgang.auftrag_id) if vorgang.auftrag_id else None

    # Eltern-Kette (aelteste zuerst); nur Vorgaenge im Sichtbereich des Nutzers.
    eltern: list[Vorgang] = []
    besucht = {vorgang.id}
    aktuelle_parent = vorgang.parent_vorgang_id
    basis = await _sichtbare_vorgaenge_stmt(session, auth, hat_recht, vorgang.id)
    while aktuelle_parent is not None and aktuelle_parent not in besucht and len(eltern) < _MAX_ELTERN_TIEFE:
        besucht.add(aktuelle_parent)
        parent = (await session.execute(basis.where(Vorgang.id == aktuelle_parent))).scalar_one_or_none()
        if parent is None:
            break
        eltern.append(parent)
        aktuelle_parent = parent.parent_vorgang_id
    eltern.reverse()

    events = list(
        (
            await session.execute(
                select(VorgangEvent)
                .where(VorgangEvent.vorgang_id == vorgang.id, VorgangEvent.event_type.in_(VERKNUEPFUNG_EVENT_TYPEN))
                .order_by(VorgangEvent.created_at, VorgangEvent.id)
            )
        )
        .scalars()
        .all()
    )

    user_ids = {u for u in (
        projekt.erstellt_von if projekt else None,
        auftrag.erstellt_von if auftrag else None,
        vorgang.erstellt_von,
        *(p.erstellt_von for p in eltern),
        *(e.author_user_id for e in events),
    ) if u}
    namen: dict[UUID, str] = {}
    if user_ids:
        zeilen = await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        namen = {z[0]: z[1] for z in zeilen}

    def person(user_id: UUID | None) -> str | None:
        return namen.get(user_id) if user_id else None

    schritte: list[HerkunftSchritt] = []
    if projekt is not None:
        schritte.append(
            HerkunftSchritt(
                art="projekt_angelegt", text=f"Projekt {projekt.name} angelegt", ref_typ="projekt", ref_id=projekt.id,
                ref_label=projekt.name, datum=projekt.created_at, person_name=person(projekt.erstellt_von),
            )
        )
    if auftrag is not None:
        # Der Auftrag kennt (noch) kein Angebot -- "aus Angebot X" entfaellt daher.
        schritte.append(
            HerkunftSchritt(
                art="auftrag_angelegt", text=f"Auftrag {auftrag.titel} angelegt", ref_typ="auftrag", ref_id=auftrag.id,
                ref_label=auftrag.titel, datum=auftrag.created_at, person_name=person(auftrag.erstellt_von),
            )
        )
    kette = [*eltern, vorgang]
    for index, glied in enumerate(kette):
        ist_folge = index > 0
        schritte.append(
            HerkunftSchritt(
                art="folge_vorgang" if ist_folge else "vorgang_angelegt",
                text=(f"Folge-Vorgang {glied.titel} entstanden" if ist_folge
                      else f"Vorgang {glied.titel} angelegt"),
                ref_typ="vorgang", ref_id=glied.id, ref_label=glied.titel, datum=glied.created_at,
                person_name=person(glied.erstellt_von), aktuell=glied.id == vorgang.id,
            )
        )
    for event in events:
        schritte.append(_event_schritt(event, person(event.author_user_id)))
    schritte.sort(key=lambda s: s.datum)

    return VorgangVerknuepfung(
        herkunft=schritte,
        rueckmeldung=await _rueckmeldung(session, vorgang),
        geschwister=await _geschwister(session, auth, hat_recht, vorgang),
        projekt=VerknuepfungProjekt(id=projekt.id, name=projekt.name) if projekt else None,
        auftrag=VerknuepfungAuftrag(id=auftrag.id, titel=auftrag.titel, status=auftrag.status) if auftrag else None,
    )


def _event_schritt(event: VorgangEvent, person_name: str | None) -> HerkunftSchritt:
    if event.event_type != "zuordnung_geaendert":
        return HerkunftSchritt(
            art=event.event_type, text=event.body or event.event_type, datum=event.created_at, person_name=person_name
        )
    neu = (event.payload or {}).get("neu") or {}
    alt = (event.payload or {}).get("alt") or {}
    ref_typ, ref_id, ref_label = None, None, None
    if neu.get("auftrag_id"):
        ref_typ, ref_id, ref_label = "auftrag", UUID(neu["auftrag_id"]), neu.get("auftrag_titel")
    elif neu.get("projekt_id"):
        ref_typ, ref_id, ref_label = "projekt", UUID(neu["projekt_id"]), neu.get("projekt_name")
    return HerkunftSchritt(
        art="zuordnung_geaendert",
        text=f"Zugeordnet zu {ref_label}" if ref_label else "Zuordnung entfernt", ref_typ=ref_typ, ref_id=ref_id, ref_label=ref_label,
        datum=event.created_at, person_name=person_name,
        zusatz=f"vorher: {_zuordnung_text({'projekt_name': alt.get('projekt_name'), 'auftrag_titel': alt.get('auftrag_titel')})}",
    )


async def _rueckmeldung(session: AsyncSession, vorgang: Vorgang) -> Rueckmeldung:
    # Nur abgeschlossene Eintraege (wie die Summe auf der Detailseite); ein
    # noch laufender Timer zaehlt erst nach dem Stoppen.
    dauer = func.coalesce(func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at)), 0)
    basis = select(dauer).where(Zeiterfassung.geloescht_am.is_(None), Zeiterfassung.ende_at.is_not(None))
    eigene = (await session.execute(basis.where(Zeiterfassung.vorgang_id == vorgang.id))).scalar_one()
    auftrag_sekunden = None
    if vorgang.auftrag_id is not None:
        auftrag_sekunden = int(
            (
                await session.execute(
                    basis.where(
                        Zeiterfassung.vorgang_id.in_(
                            select(Vorgang.id).where(
                                Vorgang.auftrag_id == vorgang.auftrag_id, Vorgang.geloescht_am.is_(None)
                            )
                        )
                    )
                )
            ).scalar_one()
        )

    # Positionen wie auf der Detailseite: Bedarfe + Materialverwendungen + LV-Buchungen.
    bedarfe = (
        await session.execute(
            select(func.count()).select_from(MaterialBedarf).where(
                MaterialBedarf.vorgang_id == vorgang.id, MaterialBedarf.geloescht_am.is_(None)
            )
        )
    ).scalar_one()
    verwendungen = (
        await session.execute(
            select(func.count()).select_from(MaterialVerwendung).where(MaterialVerwendung.vorgang_id == vorgang.id)
        )
    ).scalar_one()
    lv = (
        await session.execute(
            select(func.count()).select_from(LeistungsverzeichnisVerwendung).where(
                LeistungsverzeichnisVerwendung.vorgang_id == vorgang.id
            )
        )
    ).scalar_one()
    offene_maengel = (
        await session.execute(
            select(func.count()).select_from(Mangel).where(
                Mangel.vorgang_id == vorgang.id,
                Mangel.geloescht_am.is_(None),
                Mangel.status.not_in(("behoben", "abgelehnt")),
            )
        )
    ).scalar_one()
    return Rueckmeldung(
        arbeitszeit_sekunden=int(eigene),
        arbeitszeit_sekunden_auftrag=auftrag_sekunden,
        positionen_anzahl=bedarfe + verwendungen + lv,
        positionen_netto=None,
        offene_maengel=offene_maengel,
        status=vorgang.status,
    )


async def _geschwister(
    session: AsyncSession, auth, hat_recht: bool, vorgang: Vorgang
) -> list[VerknuepfungGeschwister]:
    stmt = await _sichtbare_vorgaenge_stmt(session, auth, hat_recht, vorgang.id)
    if vorgang.auftrag_id is not None:
        stmt = stmt.where(Vorgang.auftrag_id == vorgang.auftrag_id)
    else:
        stmt = stmt.where(Vorgang.projekt_id == vorgang.projekt_id, Vorgang.auftrag_id.is_(None))
    stmt = stmt.order_by(Vorgang.created_at, Vorgang.id)
    return [
        VerknuepfungGeschwister(
            id=v.id, vorgangsnummer=v.vorgangsnummer, titel=v.titel, status=v.status, ist_aktuell=v.id == vorgang.id
        )
        for v in (await session.execute(stmt)).scalars().all()
    ]
