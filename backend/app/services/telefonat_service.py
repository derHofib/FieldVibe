"""Telefonate (Konzept telefonate): Sichtbarkeit, Anlegen/Aendern/Loeschen samt Verlauf-Event am Vorgang,
optionaler Arbeitszeit-Buchung und automatischem Erledigen offener Rueckrufe.

Sichtbarkeit je Telefonat: mit vorgang_id gelten vorgaenge.sehen und der Vorgang-Scope (wie die Kommentare in
vorgang_events), ohne Vorgang kunden.sehen und der Kunden-Scope. Nicht sichtbare Eintraege liefern 404."""
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import Select, and_, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.models.email_log import EmailLog
from app.models.kunde import Kunde
from app.models.telefonat import Telefonat
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.telefonat import (
    KontaktverlaufEintrag,
    KontaktverlaufEmail,
    TelefonatCreate,
    TelefonatRead,
    TelefonatUpdate,
)
from app.schemas.zeiterfassung import ZeiterfassungManuellCreate, ZeiterfassungUpdate
from app.services import berechtigung_service
from app.services.audit_service import ki_schreibzugriff_protokollieren
from app.services.event_bus import event_bus
from app.services.zuweisung_service import (
    erlaubte_kunde_ids,
    require_kunde_zugriff,
    require_vorgang_zugriff,
    vorgang_scope_filter,
)


def _ist_admin(auth: AuthContext) -> bool:
    return auth.role in ("mandant_admin", "loesch_operativ")


async def sichtbar_query(session: AsyncSession, auth: AuthContext) -> Select:
    """select(Telefonat) mit Vorgang-/Kunden-Join, nur fuer den Nutzer sichtbare, nicht geloeschte Eintraege."""
    darf_vorgaenge = await berechtigung_service.hat_recht(session, auth, "vorgaenge", "sehen")
    darf_kunden = await berechtigung_service.hat_recht(session, auth, "kunden", "sehen")

    kunden_klausel = false()
    if darf_kunden:
        erlaubt = await erlaubte_kunde_ids(session, auth)
        kunden_klausel = true() if erlaubt is None else Telefonat.kunde_id.in_(erlaubt)

    vorgang_klausel = false()
    if darf_vorgaenge:
        scope = await vorgang_scope_filter(session, auth)
        vorgang_klausel = true() if scope is None else scope

    return (
        select(Telefonat)
        .outerjoin(Vorgang, Vorgang.id == Telefonat.vorgang_id)
        .outerjoin(Kunde, Kunde.id == Telefonat.kunde_id)
        .where(
            Telefonat.geloescht_am.is_(None),
            or_(
                and_(Telefonat.vorgang_id.is_(None), Kunde.geloescht_am.is_(None), kunden_klausel),
                and_(Telefonat.vorgang_id.is_not(None), Vorgang.geloescht_am.is_(None), vorgang_klausel),
            ),
        )
    )


async def _lesemodelle(session: AsyncSession, telefonate: list[Telefonat]) -> list[TelefonatRead]:
    """Reichert die Zeilen um Kunden-/Vorgangs-/Erfasser-Namen an (je ein Batch statt N+1)."""
    if not telefonate:
        return []
    kunde_ids = {t.kunde_id for t in telefonate if t.kunde_id}
    vorgang_ids = {t.vorgang_id for t in telefonate if t.vorgang_id}
    user_ids = {t.erfasst_von for t in telefonate}
    zeit_ids = {t.zeiterfassung_id for t in telefonate if t.zeiterfassung_id}

    kunden = dict((await session.execute(select(Kunde.id, Kunde.name).where(Kunde.id.in_(kunde_ids)))).all())
    vorgaenge = {
        r.id: r
        for r in (
            await session.execute(
                select(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel).where(Vorgang.id.in_(vorgang_ids))
            )
        ).all()
    }
    users = dict((await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all())
    # Ein ueber die Zeitseite geloeschter Eintrag zaehlt nicht mehr als gebucht.
    aktive_zeit = set(
        (
            await session.execute(
                select(Zeiterfassung.id).where(Zeiterfassung.id.in_(zeit_ids), Zeiterfassung.geloescht_am.is_(None))
            )
        ).scalars()
    )

    ergebnis = []
    for t in telefonate:
        daten = TelefonatRead.model_validate(t)
        daten.kunde_name = kunden.get(t.kunde_id)
        v = vorgaenge.get(t.vorgang_id)
        daten.vorgang_nummer = v.vorgangsnummer if v else None
        daten.vorgang_titel = v.titel if v else None
        daten.erfasst_von_name = users.get(t.erfasst_von)
        if t.zeiterfassung_id not in aktive_zeit:
            daten.zeiterfassung_id = None
        ergebnis.append(daten)
    return ergebnis


async def lesen(session: AsyncSession, auth: AuthContext, telefonat_id: UUID) -> Telefonat:
    t = (
        await session.execute((await sichtbar_query(session, auth)).where(Telefonat.id == telefonat_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telefonat nicht gefunden")
    return t


async def lesemodell(session: AsyncSession, auth: AuthContext, telefonat_id: UUID) -> TelefonatRead:
    return (await _lesemodelle(session, [await lesen(session, auth, telefonat_id)]))[0]


async def liste(
    session: AsyncSession,
    auth: AuthContext,
    *,
    kunde_id: UUID | None,
    vorgang_id: UUID | None,
    rueckruf_offen: bool,
    von_mir: bool,
    ergebnis: str | None,
    seite: int,
    limit: int,
) -> list[TelefonatRead]:
    stmt = await sichtbar_query(session, auth)
    if kunde_id is not None:
        stmt = stmt.where(Telefonat.kunde_id == kunde_id)
    if vorgang_id is not None:
        stmt = stmt.where(Telefonat.vorgang_id == vorgang_id)
    if von_mir:
        stmt = stmt.where(Telefonat.erfasst_von == auth.user_id)
    if ergebnis is not None:
        stmt = stmt.where(Telefonat.ergebnis == ergebnis)
    if rueckruf_offen:
        stmt = stmt.where(Telefonat.rueckruf_am.is_not(None), Telefonat.rueckruf_erledigt_am.is_(None)).order_by(
            Telefonat.rueckruf_am.asc(), Telefonat.id
        )
    else:
        stmt = stmt.order_by(Telefonat.beginn.desc(), Telefonat.id)
    stmt = stmt.limit(limit).offset((seite - 1) * limit)
    return await _lesemodelle(session, list((await session.execute(stmt)).scalars()))


async def anzahl_offene_rueckrufe(session: AsyncSession, auth: AuthContext) -> int:
    sub = (await sichtbar_query(session, auth)).where(
        Telefonat.erfasst_von == auth.user_id,
        Telefonat.rueckruf_am.is_not(None),
        Telefonat.rueckruf_erledigt_am.is_(None),
    )
    return (await session.execute(select(func.count()).select_from(sub.subquery()))).scalar_one()


def _iso(wert: datetime | None) -> str | None:
    return wert.isoformat() if wert else None


def _event_felder(t: Telefonat, *, zeit_gebucht: bool) -> dict[str, Any]:
    return {
        "telefonat_id": str(t.id),
        "richtung": t.richtung,
        "ergebnis": t.ergebnis,
        "beginn": _iso(t.beginn),
        "dauer_sekunden": t.dauer_sekunden,
        "partner_name": t.partner_name,
        "partner_nummer": t.partner_nummer,
        "rueckruf_am": _iso(t.rueckruf_am),
        "rueckruf_erledigt_am": _iso(t.rueckruf_erledigt_am),
        "zeit_gebucht": zeit_gebucht,
    }


async def _event_zu(session: AsyncSession, telefonat_id: UUID) -> VorgangEvent | None:
    return (
        await session.execute(
            select(VorgangEvent).where(
                VorgangEvent.ref_entity_type == "telefonat", VorgangEvent.ref_entity_id == telefonat_id
            )
        )
    ).scalar_one_or_none()


async def _event_aktualisieren(session: AsyncSession, t: Telefonat) -> None:
    if t.vorgang_id is None:
        return
    event = await _event_zu(session, t.id)
    if event is None:
        return
    event.body = t.notiz
    # Neues Dict statt In-Place-Aenderung, sonst erkennt SQLAlchemy die JSONB-Aenderung nicht;
    # "via"/"ki_verbindung_id" bleiben aus dem alten Payload erhalten.
    event.payload = {**event.payload, **_event_felder(t, zeit_gebucht=t.zeiterfassung_id is not None)}


async def _zeit_anlegen(session: AsyncSession, auth: AuthContext, t: Telefonat) -> UUID:
    from app.api.routes.zeiterfassung import manuellen_eintrag_anlegen  # Sperren/Protokoll nicht duplizieren

    try:
        body = ZeiterfassungManuellCreate(
            start_at=t.beginn,
            ende_at=t.beginn + timedelta(seconds=t.dauer_sekunden or 0),
            kategorie="auftrag",
            vorgang_id=t.vorgang_id,
            taetigkeit=f"Telefonat mit {t.partner_name}",
            abrechenbar=True,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Arbeitszeit nicht buchbar: {exc.errors()[0]['msg'].removeprefix('Value error, ')}",
        ) from exc
    eintrag = await manuellen_eintrag_anlegen(body, auth, session)
    return eintrag.id


async def anlegen(
    session: AsyncSession, auth: AuthContext, body: TelefonatCreate
) -> tuple[TelefonatRead, bool]:
    """Gibt (Telefonat, neu_angelegt) zurueck; bei bekannter client_uuid der bestehende Eintrag mit neu=False."""
    if body.client_uuid is not None:
        # Vorab geprueft statt als IntegrityError abgefangen: ein fehlgeschlagener Flush wuerde die ganze
        # Request-Transaktion abbrechen, und der Wiederholungsfall der Offline-Outbox ist der Normalfall.
        vorhanden = (
            await session.execute(select(Telefonat).where(Telefonat.client_uuid == body.client_uuid))
        ).scalar_one_or_none()
        if vorhanden is not None:
            if vorhanden.erfasst_von != auth.user_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="client_uuid bereits vergeben")
            return (await _lesemodelle(session, [vorhanden]))[0], False

    kunde_id = body.kunde_id
    if body.vorgang_id is not None:
        if not await berechtigung_service.hat_recht(session, auth, "vorgaenge", "sehen"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        vorgang = await session.get(Vorgang, body.vorgang_id)
        if vorgang is None or vorgang.geloescht_am is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
        await require_vorgang_zugriff(session, auth, vorgang)
        if kunde_id is not None and kunde_id != vorgang.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Die Kunden-ID passt nicht zum Vorgang",
            )
        kunde_id = vorgang.kunde_id
    else:
        if not await berechtigung_service.hat_recht(session, auth, "kunden", "sehen"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")
        kunde = await session.get(Kunde, kunde_id)
        if kunde is None or kunde.geloescht_am is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
        await require_kunde_zugriff(session, auth, kunde_id, "Kunde nicht gefunden")

    erreicht = body.ergebnis == "erreicht"
    t = Telefonat(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        vorgang_id=body.vorgang_id,
        ansprechpartner_id=body.ansprechpartner_id,
        partner_name=body.partner_name,
        partner_nummer=(body.partner_nummer or "").strip() or None,
        richtung=body.richtung,
        ergebnis=body.ergebnis,
        erstellt_via="claude" if auth.via == "mcp" else "app",
        beginn=body.beginn,
        # Bei "nicht erreicht"/Mailbox gibt es keine Gespraechsdauer.
        dauer_sekunden=body.dauer_sekunden if erreicht else None,
        notiz=(body.notiz or "").strip() or None,
        rueckruf_am=body.rueckruf_am,
        erfasst_von=auth.user_id,
        client_uuid=body.client_uuid,
    )
    session.add(t)
    await session.flush()

    if body.als_arbeitszeit_buchen:
        t.zeiterfassung_id = await _zeit_anlegen(session, auth, t)

    if erreicht:
        await _rueckrufe_erledigen(session, t)

    if t.vorgang_id is not None:
        payload = _event_felder(t, zeit_gebucht=t.zeiterfassung_id is not None)
        # Techniker haben keine Nutzerliste im Frontend, daher den Namen im Event mitgeben.
        erfasser = await session.get(User, t.erfasst_von)
        payload["erfasst_von_name"] = erfasser.name if erfasser else None
        if t.erstellt_via == "claude":
            payload["via"] = "claude"
            if auth.ki_verbindung_id is not None:
                payload["ki_verbindung_id"] = str(auth.ki_verbindung_id)
        event = VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=t.vorgang_id,
            event_type="telefonat",
            author_user_id=auth.user_id,
            body=t.notiz,
            payload=payload,
            ref_entity_type="telefonat",
            ref_entity_id=t.id,
            kundensichtbar=False,
        )
        session.add(event)
        await session.flush()
        await event_bus.publish(
            auth.mandant_id,
            "vorgang_event",
            {"vorgang_id": str(t.vorgang_id), "event_id": event.id, "event_type": "telefonat"},
        )

    await ki_schreibzugriff_protokollieren(
        session, auth, aktion="ki_telefonat_angelegt", entity_type="telefonat", entity_id=t.id,
        payload={"vorgang_id": t.vorgang_id, "kunde_id": t.kunde_id},
    )
    await session.refresh(t)
    return (await _lesemodelle(session, [t]))[0], True


async def _rueckrufe_erledigen(session: AsyncSession, neu: Telefonat) -> None:
    """Ein erreichtes Gespraech mit demselben Partner (Ansprechpartner-Id oder gleiche Nummer) erledigt die
    offenen Rueckrufe dieses Kunden zu diesem Partner."""
    partner = []
    if neu.ansprechpartner_id is not None:
        partner.append(Telefonat.ansprechpartner_id == neu.ansprechpartner_id)
    nummer = (neu.partner_nummer or "").replace(" ", "")
    if nummer:
        partner.append(func.replace(Telefonat.partner_nummer, " ", "") == nummer)
    if not partner or neu.kunde_id is None:
        return
    offene = (
        await session.execute(
            select(Telefonat).where(
                Telefonat.kunde_id == neu.kunde_id,
                Telefonat.id != neu.id,
                Telefonat.geloescht_am.is_(None),
                Telefonat.rueckruf_am.is_not(None),
                Telefonat.rueckruf_erledigt_am.is_(None),
                or_(*partner),
            )
        )
    ).scalars().all()
    jetzt = datetime.now(UTC)
    for t in offene:
        t.rueckruf_erledigt_am = jetzt
        await _event_aktualisieren(session, t)


def _pruefe_aenderungsrecht(auth: AuthContext, t: Telefonat) -> None:
    if t.erfasst_von != auth.user_id and not _ist_admin(auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur der Erfasser oder ein Administrator darf dieses Telefonat ändern",
        )


def _zeit_konflikt(exc: HTTPException, praefix: str) -> HTTPException:
    if exc.status_code != status.HTTP_409_CONFLICT:
        return exc
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{praefix} ({exc.detail})")


async def aktualisieren(
    session: AsyncSession, auth: AuthContext, telefonat_id: UUID, body: TelefonatUpdate
) -> TelefonatRead:
    t = await lesen(session, auth, telefonat_id)
    _pruefe_aenderungsrecht(auth, t)
    daten = body.model_dump(exclude_unset=True)
    erledigt = daten.pop("rueckruf_erledigt", None)

    neues_ergebnis = daten.get("ergebnis", t.ergebnis)
    neue_notiz = (daten["notiz"] if "notiz" in daten else t.notiz) or ""
    if neues_ergebnis == "erreicht" and not neue_notiz.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bei einem erreichten Gespräch ist eine Notiz Pflicht",
        )
    neue_dauer = daten.get("dauer_sekunden", t.dauer_sekunden) if neues_ergebnis == "erreicht" else None
    if t.zeiterfassung_id is not None and (neues_ergebnis != "erreicht" or not neue_dauer):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Für dieses Telefonat ist Arbeitszeit gebucht; Ergebnis und Dauer müssen dazu passen",
        )

    # Zuerst die Arbeitszeit: lehnt sie die Aenderung ab (gebucht/abgerechnet), bleibt das Telefonat unberuehrt.
    neuer_beginn = daten.get("beginn", t.beginn)
    zeit_aendert = t.zeiterfassung_id is not None and (
        neuer_beginn != t.beginn or neue_dauer != t.dauer_sekunden or daten.get("partner_name", t.partner_name) != t.partner_name
    )
    if zeit_aendert:
        from app.api.routes.zeiterfassung import zeiterfassung_aktualisieren

        try:
            await zeiterfassung_aktualisieren(
                t.zeiterfassung_id,
                ZeiterfassungUpdate(
                    start_at=neuer_beginn,
                    ende_at=neuer_beginn + timedelta(seconds=neue_dauer or 0),
                    taetigkeit=f"Telefonat mit {daten.get('partner_name', t.partner_name)}",
                    grund="Telefonat geändert",
                ),
                auth,
                session,
            )
        except HTTPException as exc:
            raise _zeit_konflikt(exc, "Die gebuchte Arbeitszeit lässt sich nicht mehr anpassen") from exc

    for feld, wert in daten.items():
        if feld in ("notiz", "partner_nummer"):
            wert = (wert or "").strip() or None
        setattr(t, feld, wert)
    t.dauer_sekunden = neue_dauer
    if "rueckruf_am" in daten:
        t.rueckruf_benachrichtigt_am = None
    if erledigt is True and t.rueckruf_erledigt_am is None:
        t.rueckruf_erledigt_am = datetime.now(UTC)
    elif erledigt is False:
        t.rueckruf_erledigt_am = None

    await session.flush()
    await _event_aktualisieren(session, t)
    if t.vorgang_id is not None:
        await event_bus.publish(
            auth.mandant_id, "vorgang_event", {"vorgang_id": str(t.vorgang_id), "event_type": "telefonat"}
        )
    await session.refresh(t)
    return (await _lesemodelle(session, [t]))[0]


async def loeschen(session: AsyncSession, auth: AuthContext, telefonat_id: UUID) -> None:
    t = await lesen(session, auth, telefonat_id)
    _pruefe_aenderungsrecht(auth, t)

    if t.zeiterfassung_id is not None:
        eintrag = await session.get(Zeiterfassung, t.zeiterfassung_id)
        if eintrag is not None and eintrag.geloescht_am is None:
            from app.api.routes.zeiterfassung import zeiterfassung_loeschen

            try:
                await zeiterfassung_loeschen(eintrag.id, "Telefonat gelöscht", auth, session)
            except HTTPException as exc:
                raise _zeit_konflikt(exc, "Die gebuchte Arbeitszeit lässt sich nicht mehr löschen") from exc

    t.geloescht_am = datetime.now(UTC)
    t.geloescht_von = auth.user_id
    event = await _event_zu(session, t.id)
    if event is not None:
        await session.delete(event)
    await session.flush()
    if t.vorgang_id is not None:
        await event_bus.publish(
            auth.mandant_id, "vorgang_event", {"vorgang_id": str(t.vorgang_id), "event_type": "telefonat"}
        )


async def kontaktverlauf(
    session: AsyncSession, auth: AuthContext, kunde_id: UUID, limit: int
) -> list[KontaktverlaufEintrag]:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await require_kunde_zugriff(session, auth, kunde_id, "Kunde nicht gefunden")

    telefonate = await _lesemodelle(
        session,
        list(
            (
                await session.execute(
                    (await sichtbar_query(session, auth))
                    .where(Telefonat.kunde_id == kunde_id)
                    .order_by(Telefonat.beginn.desc(), Telefonat.id)
                    .limit(limit)
                )
            ).scalars()
        ),
    )

    # E-Mails: direkt am Kunden oder an dessen Vorgaengen (nur Vorgaenge, die der Nutzer sehen darf).
    ziele = [and_(EmailLog.entity_type == "kunde", EmailLog.entity_id == kunde_id)]
    if await berechtigung_service.hat_recht(session, auth, "vorgaenge", "sehen"):
        scope = await vorgang_scope_filter(session, auth)
        vorgang_ids = select(Vorgang.id).where(Vorgang.kunde_id == kunde_id, Vorgang.geloescht_am.is_(None))
        if scope is not None:
            vorgang_ids = vorgang_ids.where(scope)
        ziele.append(and_(EmailLog.entity_type == "vorgang", EmailLog.entity_id.in_(vorgang_ids)))
    mails = (
        await session.execute(
            select(EmailLog, Vorgang.id, Vorgang.vorgangsnummer)
            .outerjoin(Vorgang, and_(EmailLog.entity_type == "vorgang", Vorgang.id == EmailLog.entity_id))
            .where(or_(*ziele))
            .order_by(EmailLog.created_at.desc())
            .limit(limit)
        )
    ).all()

    eintraege = [KontaktverlaufEintrag(art="telefonat", zeit=t.beginn, telefonat=t) for t in telefonate]
    for mail, vorgang_id, nummer in mails:
        eintraege.append(
            KontaktverlaufEintrag(
                art="email",
                zeit=mail.created_at,
                email=KontaktverlaufEmail(
                    id=mail.id,
                    betreff=mail.betreff,
                    empfaenger=mail.empfaenger,
                    status=mail.status,
                    vorgang_id=vorgang_id,
                    vorgang_nummer=nummer,
                    gesendet_am=mail.created_at if mail.status == "gesendet" else None,
                    created_at=mail.created_at,
                ),
            )
        )
    eintraege.sort(key=lambda e: e.zeit, reverse=True)
    return eintraege[:limit]
