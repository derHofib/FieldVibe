"""Rechnungsarten: Rechnung aus Angebot, Abschlag, Schlussrechnung (Anrechnung
der Abschlaege) und Gutschrift.

Abschlaege werden NETTO angerechnet: die Schlussrechnung traegt je Abschlag
eine Abzugsposition mit negativem Nettobetrag und -- je Steuergruppe -- den
Steuerfeldern der Abschlagsrechnung. Die Gruppenrechnung des Steuerkerns
(steuer_service.steuer_gruppen) ergibt damit von selbst die Rest-Steuer; die
USt der Abschlaege wurde bereits mit diesen Rechnungen ausgewiesen.

"Nicht storniert" heisst durchgehend: status != 'storniert', nicht im
Papierkorb und kein Storno-Beleg. Entwuerfe zaehlen mit -- ein Abschlag im
Entwurf belegt sein Kontingent, bis er versendet oder geloescht wird."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.rechnung import (
    AbschlaegeAnrechnen,
    GutschriftCreate,
    RechnungAusAngebotCreate,
)
from app.services import angebot_service, rechnung_service, steuer_service
from app.services.numbering_service import next_rechnungsnummer

_NULL = Decimal("0")
ABSCHLAG_EINHEIT = "psch"
# Abschlaege, die schon beim Kunden sind -- nur diese duerfen angerechnet werden.
_ANRECHENBARE_STATUS = ("versendet", "teilweise_bezahlt", "bezahlt")
_ERLAUBTE_GUTSCHRIFT_STATUS = ("versendet", "teilweise_bezahlt", "bezahlt")

RECHNUNGSART_LABEL = {
    "rechnung": "Rechnung",
    "abschlag": "Abschlagsrechnung",
    "schluss": "Schlussrechnung",
    "gutschrift": "Gutschrift",
}


def rechnungsart_label(rechnung: Rechnung) -> str:
    return RECHNUNGSART_LABEL.get(rechnung.rechnungsart, "Rechnung")


def _konflikt(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unverarbeitbar(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _datum(wert: datetime) -> str:
    return wert.strftime("%d.%m.%Y")


def _euro(betrag: Decimal) -> str:
    text = f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _prozent(wert: Decimal) -> str:
    text = f"{wert:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def nicht_storniert() -> list:
    return [Rechnung.status != "storniert", Rechnung.geloescht_am.is_(None), Rechnung.ist_storno.is_(False)]


# --- Abfragen -------------------------------------------------------------------


async def _belege_zum_angebot(session: AsyncSession, angebot_id: UUID, arten: tuple[str, ...]) -> list[Rechnung]:
    result = await session.execute(
        select(Rechnung)
        .where(Rechnung.angebot_id == angebot_id, Rechnung.rechnungsart.in_(arten), *nicht_storniert())
        .order_by(Rechnung.created_at, Rechnung.id)
    )
    return list(result.scalars().all())


async def netto_von(session: AsyncSession, rechnung: Rechnung) -> Decimal:
    return rechnung_service.netto_betrag(rechnung, await rechnung_service.positionen_fuer(session, rechnung.id))


async def abschlag_angerechnet_in(
    session: AsyncSession, abschlag_ids: list[UUID], *, ausser_rechnung_id: UUID | None = None
) -> dict[UUID, Rechnung]:
    """Abschlag -> nicht stornierte Rechnung (Schluss oder Entwurf), die ihn
    anrechnet. Ein Abschlag darf nur einmal angerechnet werden."""
    if not abschlag_ids:
        return {}
    stmt = (
        select(RechnungPosition.abschlag_rechnung_id, Rechnung)
        .join(Rechnung, Rechnung.id == RechnungPosition.rechnung_id)
        .where(RechnungPosition.abschlag_rechnung_id.in_(abschlag_ids), *nicht_storniert())
    )
    if ausser_rechnung_id is not None:
        stmt = stmt.where(Rechnung.id != ausser_rechnung_id)
    return {abschlag_id: rechnung for abschlag_id, rechnung in (await session.execute(stmt)).all()}


async def gutschriften_zu(session: AsyncSession, rechnung_id: UUID) -> list[Rechnung]:
    """Nicht stornierte Gutschriften zu einer Rechnung, aelteste zuerst."""
    result = await session.execute(
        select(Rechnung)
        .where(
            Rechnung.bezug_rechnung_id == rechnung_id,
            Rechnung.rechnungsart == "gutschrift",
            Rechnung.status != "storniert",
            Rechnung.geloescht_am.is_(None),
        )
        .order_by(Rechnung.created_at, Rechnung.id)
    )
    return list(result.scalars().all())


# --- Anlage aus dem Angebot -----------------------------------------------------


def _steuer_aus_angebot(angebot: Angebot, mandant: Mandant) -> steuer_service.PositionSteuer:
    try:
        return steuer_service.loese_steuer_auf(
            kategorie=None,
            satz=None,
            beleg_mwst_satz=angebot.mwst_satz,
            kleinunternehmer=steuer_service.ist_kleinunternehmer(mandant),
        )
    except steuer_service.SteuerFehler as exc:
        raise _unverarbeitbar(str(exc)) from exc


def _position(
    rechnung: Rechnung,
    nummer: int,
    *,
    beschreibung: str,
    menge: Decimal,
    einheit: str,
    einzelpreis: Decimal,
    steuer: steuer_service.PositionSteuer,
    **extra,
) -> RechnungPosition:
    return RechnungPosition(
        mandant_id=rechnung.mandant_id,
        rechnung_id=rechnung.id,
        position=nummer,
        beschreibung=beschreibung,
        menge=menge,
        einheit=einheit,
        einzelpreis=einzelpreis,
        steuer_kategorie=steuer.kategorie,
        steuer_satz=steuer.satz,
        steuer_grund=steuer.grund,
        steuer_grund_text=steuer.grund_text,
        **extra,
    )


async def _abzugspositionen(
    session: AsyncSession,
    rechnung: Rechnung,
    abschlaege: list[Rechnung],
    start: int,
    gruppen_ids: frozenset[UUID] = frozenset(),
) -> int:
    """Je Abschlag eine Abzugsposition (bei Abschlaegen mit mehreren
    Steuergruppen je Gruppe eine). Gibt die naechste freie Positionsnummer
    zurueck. gruppen_ids sind die Vorgaenge, nach denen die PDF die Positionen
    des Entwurfs gruppiert: der Abzug gehoert in die Gruppe seines Abschlags,
    damit er nicht als einzelne Zeile vor allen Gruppen steht."""
    nummer = start
    for abschlag in abschlaege:
        positionen = await rechnung_service.positionen_fuer(session, abschlag.id)
        gruppen = steuer_service.steuer_gruppen(abschlag, positionen)
        grund_von: dict[tuple[str, Decimal], RechnungPosition] = {}
        for p in positionen:
            grund_von.setdefault((p.steuer_kategorie, p.steuer_satz.quantize(Decimal("0.01"))), p)
        vorgang_id = next(
            (v for v in (abschlag.vorgang_id, rechnung.vorgang_id) if v is not None and v in gruppen_ids), None
        )
        text = f"Abzüglich Abschlagsrechnung {abschlag.rechnungsnummer} vom {_datum(abschlag.created_at)} (netto)"
        for gruppe in gruppen:
            quelle = grund_von.get((gruppe.kategorie, gruppe.satz))
            steuer = steuer_service.PositionSteuer(
                gruppe.kategorie,
                gruppe.satz,
                quelle.steuer_grund if quelle else None,
                quelle.steuer_grund_text if quelle else None,
            )
            session.add(
                _position(
                    rechnung,
                    nummer,
                    beschreibung=text if len(gruppen) == 1 else f"{text} – {_prozent(gruppe.satz)} % USt.",
                    menge=Decimal("1"),
                    einheit=ABSCHLAG_EINHEIT,
                    einzelpreis=-gruppe.netto,
                    steuer=steuer,
                    abschlag_rechnung_id=abschlag.id,
                    vorgang_id=vorgang_id,
                )
            )
            nummer += 1
    return nummer


async def _vorgangs_event(session: AsyncSession, rechnung: Rechnung, actor_user_id: UUID, body: str) -> None:
    if rechnung.vorgang_id is None:
        return
    session.add(
        VorgangEvent(
            mandant_id=rechnung.mandant_id,
            vorgang_id=rechnung.vorgang_id,
            event_type="rechnung_status",
            author_user_id=actor_user_id,
            body=body,
            payload={"rechnung_id": str(rechnung.id), "status": rechnung.status},
        )
    )


async def rechnung_aus_angebot(
    session: AsyncSession, body: RechnungAusAngebotCreate, *, mandant: Mandant, actor_user_id: UUID
) -> Rechnung:
    # Sperre auf dem Angebot: zwei gleichzeitige Anlagen (Abschlaege!) sehen
    # sonst beide denselben Stand und ueberschreiten gemeinsam die 100 %.
    angebot = (
        await session.execute(
            select(Angebot).where(Angebot.id == body.angebot_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    if angebot.status != "angenommen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur angenommene Angebote können abgerechnet werden"
        )
    angebot_positionen = await angebot_service.positionen_fuer(session, angebot.id)
    if not angebot_positionen:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Das Angebot hat keine Positionen")
    angebot_netto, _ = angebot_service.summen(angebot_positionen, angebot.mwst_satz)
    steuer = _steuer_aus_angebot(angebot, mandant)

    vollrechnungen = await _belege_zum_angebot(session, angebot.id, ("rechnung", "schluss"))
    abschlaege = await _belege_zum_angebot(session, angebot.id, ("abschlag",))
    abschlag_nettos = {a.id: await netto_von(session, a) for a in abschlaege}

    art = body.rechnungsart
    if art in ("rechnung", "schluss") and vollrechnungen:
        raise _konflikt(
            f"Zu diesem Angebot existiert bereits die {rechnungsart_label(vollrechnungen[0])} "
            f"{vollrechnungen[0].rechnungsnummer}"
        )
    if art == "rechnung" and abschlaege:
        raise _konflikt(
            "Zu diesem Angebot existieren bereits Abschlagsrechnungen – bitte eine Schlussrechnung erstellen"
        )
    if art == "abschlag" and vollrechnungen:
        raise _konflikt(
            f"Zu diesem Angebot existiert bereits die {rechnungsart_label(vollrechnungen[0])} "
            f"{vollrechnungen[0].rechnungsnummer}; weitere Abschläge sind nicht möglich"
        )

    abschlag_betrag = None
    if art == "abschlag":
        if body.abschlag_prozent is not None:
            abschlag_betrag = steuer_service.runde_cent(angebot_netto * body.abschlag_prozent / Decimal("100"))
        else:
            abschlag_betrag = steuer_service.runde_cent(body.abschlag_netto)
        if abschlag_betrag <= 0:
            raise _unverarbeitbar("Der Abschlagsbetrag muss größer als 0 sein")
        bisher = sum(abschlag_nettos.values(), _NULL)
        if bisher + abschlag_betrag > angebot_netto:
            raise _unverarbeitbar(
                "Mit diesem Abschlag wären mehr als 100 % des Angebots abgerechnet "
                f"(bereits abgerechnet: {_euro(bisher)}, Rest: {_euro(max(angebot_netto - bisher, _NULL))})"
            )

    zu_rechnen: list[Rechnung] = []
    if art == "schluss":
        for abschlag in abschlaege:
            if abschlag.status == "entwurf":
                raise _konflikt(f"Abschlag {abschlag.rechnungsnummer} ist noch nicht versendet")
        angerechnet = await abschlag_angerechnet_in(session, [a.id for a in abschlaege])
        for abschlag in abschlaege:
            if abschlag.id in angerechnet:
                raise _konflikt(
                    f"Abschlag {abschlag.rechnungsnummer} ist bereits in Rechnung "
                    f"{angerechnet[abschlag.id].rechnungsnummer} angerechnet"
                )
        zu_rechnen = abschlaege

    rechnung = Rechnung(
        mandant_id=angebot.mandant_id,
        kunde_id=angebot.kunde_id,
        vorgang_id=angebot.auftrag_vorgang_id or angebot.vorgang_id,
        rechnungsnummer=await next_rechnungsnummer(session, angebot.mandant_id),
        betrag_netto=_NULL,
        mwst_satz=_NULL if steuer_service.ist_kleinunternehmer(mandant) else angebot.mwst_satz,
        faellig_am=body.faellig_am,
        leistungsdatum=body.leistungsdatum,
        erstellt_von=actor_user_id,
        rechnungsart=art,
        angebot_id=angebot.id,
    )
    session.add(rechnung)
    await session.flush()

    if art == "abschlag":
        beschreibung = (
            f"Abschlagszahlung {_prozent(body.abschlag_prozent)} % auf Angebot {angebot.angebotsnummer}"
            if body.abschlag_prozent is not None
            else f"Abschlagszahlung auf Angebot {angebot.angebotsnummer}"
        )
        session.add(
            _position(
                rechnung,
                1,
                beschreibung=beschreibung,
                menge=Decimal("1"),
                einheit=ABSCHLAG_EINHEIT,
                einzelpreis=abschlag_betrag,
                steuer=steuer,
            )
        )
    else:
        nummer = 1
        for p in angebot_positionen:
            session.add(
                _position(
                    rechnung,
                    nummer,
                    beschreibung=p.beschreibung,
                    menge=p.menge,
                    einheit=p.einheit,
                    einzelpreis=p.einzelpreis,
                    steuer=steuer,
                )
            )
            nummer += 1
        await _abzugspositionen(session, rechnung, zu_rechnen, nummer)
    await session.flush()
    await session.refresh(rechnung)
    await _vorgangs_event(
        session,
        rechnung,
        actor_user_id,
        f"{rechnungsart_label(rechnung)} {rechnung.rechnungsnummer} aus Angebot {angebot.angebotsnummer} erstellt (Entwurf)",
    )
    return rechnung


# --- Anrechnung an einem beliebigen Entwurf --------------------------------------


async def abschlaege_anrechnen(
    session: AsyncSession, rechnung: Rechnung, body: AbschlaegeAnrechnen
) -> int:
    """Macht den Entwurf zur Schlussrechnung und haengt Abzugspositionen an.
    Gibt die Anzahl angerechneter Abschlaege zurueck."""
    bezug_bedingungen = []
    if rechnung.angebot_id is not None:
        bezug_bedingungen.append(Rechnung.angebot_id == rechnung.angebot_id)
    if rechnung.vorgang_id is not None:
        bezug_bedingungen.append(Rechnung.vorgang_id == rechnung.vorgang_id)
    kandidaten: list[Rechnung] = []
    if bezug_bedingungen:
        # Sperre auf den Abschlaegen: zwei Entwuerfe duerfen denselben Abschlag
        # nicht gleichzeitig anrechnen.
        kandidaten = list(
            (
                await session.execute(
                    select(Rechnung)
                    .where(
                        Rechnung.kunde_id == rechnung.kunde_id,
                        Rechnung.rechnungsart == "abschlag",
                        Rechnung.id != rechnung.id,
                        or_(*bezug_bedingungen),
                        *nicht_storniert(),
                    )
                    .order_by(Rechnung.created_at, Rechnung.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
    angerechnet = await abschlag_angerechnet_in(session, [a.id for a in kandidaten])

    if body.abschlag_rechnung_ids is not None:
        nach_id = {a.id: a for a in kandidaten}
        gewaehlt = []
        for abschlag_id in dict.fromkeys(body.abschlag_rechnung_ids):
            abschlag = nach_id.get(abschlag_id)
            if abschlag is None:
                raise _unverarbeitbar(
                    f"Abschlag {abschlag_id} kann nicht angerechnet werden "
                    "(nicht gefunden, storniert oder passt nicht zu Kunde, Angebot bzw. Vorgang der Rechnung)"
                )
            gewaehlt.append(abschlag)
        for abschlag in gewaehlt:
            if abschlag.status == "entwurf":
                raise _konflikt(f"Abschlag {abschlag.rechnungsnummer} ist noch nicht versendet")
            if abschlag.id in angerechnet:
                raise _konflikt(
                    f"Abschlag {abschlag.rechnungsnummer} ist bereits in Rechnung "
                    f"{angerechnet[abschlag.id].rechnungsnummer} angerechnet"
                )
    else:
        gewaehlt = [a for a in kandidaten if a.status in _ANRECHENBARE_STATUS and a.id not in angerechnet]

    if not gewaehlt:
        offene = [a.rechnungsnummer for a in kandidaten if a.status == "entwurf" and a.id not in angerechnet]
        hinweis = f" (Abschlag {', '.join(offene)} ist noch nicht versendet)" if offene else ""
        raise _konflikt("Keine anrechenbaren Abschlagsrechnungen gefunden" + hinweis)

    bestehende = await rechnung_service.positionen_fuer(session, rechnung.id)
    start = max((p.position for p in bestehende), default=0) + 1
    await _abzugspositionen(
        session, rechnung, gewaehlt, start, frozenset(p.vorgang_id for p in bestehende if p.vorgang_id is not None)
    )
    rechnung.rechnungsart = "schluss"
    await session.flush()
    return len(gewaehlt)


# --- Gutschrift -----------------------------------------------------------------


async def erstelle_gutschrift(
    session: AsyncSession,
    original: Rechnung,
    body: GutschriftCreate,
    *,
    mandant: Mandant,
    actor_user_id: UUID,
) -> Rechnung:
    """Teil- oder Voll-Gutschrift zu einer versendeten Rechnung. Anders als der
    Komplett-Storno (erstelle_stornorechnung) bleibt das Original gueltig; die
    Gutschrift senkt dessen offenen Betrag (rechnung_service, Offene-Posten-
    Regel). Zeiterfassung und Material bleiben gesperrt -- die Leistung wurde
    erbracht, nur der Betrag wird zurueckgenommen."""
    if original.status not in _ERLAUBTE_GUTSCHRIFT_STATUS:
        raise _konflikt("Gutschriften sind nur zu versendeten, teilweise bezahlten oder bezahlten Rechnungen möglich")
    if original.ist_storno:
        raise _konflikt("Zu einer Stornorechnung kann keine Gutschrift erstellt werden")
    if original.rechnungsart == "gutschrift":
        raise _konflikt("Zu einer Gutschrift kann keine weitere Gutschrift erstellt werden")
    if original.rechnungsart == "abschlag":
        raise _konflikt(
            "Zu einer Abschlagsrechnung kann keine Gutschrift erstellt werden – "
            "bitte die Abschlagsrechnung stornieren und neu stellen"
        )

    # Sperre auf dem Original: parallele Gutschriften duerfen die Mengen-
    # Obergrenze nicht gemeinsam ueberschreiten.
    await session.execute(
        select(Rechnung).where(Rechnung.id == original.id).with_for_update().execution_options(populate_existing=True)
    )
    original_positionen = await rechnung_service.positionen_fuer(session, original.id)
    bisherige = await gutschriften_zu(session, original.id)
    bisherige_positionen = await rechnung_service.positionen_fuer_mehrere(session, [g.id for g in bisherige])
    gutgeschrieben: dict[UUID, Decimal] = {}
    for g in bisherige:
        for p in bisherige_positionen.get(g.id, []):
            if p.bezug_position_id is not None:
                gutgeschrieben[p.bezug_position_id] = gutgeschrieben.get(p.bezug_position_id, _NULL) + p.menge

    auswahl: list[tuple[RechnungPosition | None, Decimal]] = []
    if not original_positionen:
        # Einfacher Beleg (nur betrag_netto): es gibt nichts Positionsweises.
        if not body.alle:
            raise _unverarbeitbar("Diese Rechnung hat keine Positionen – bitte „alle“ verwenden")
        if bisherige:
            raise _konflikt("Zu dieser Rechnung existiert bereits eine Gutschrift")
        auswahl.append((None, Decimal("1")))
    elif body.alle:
        for p in original_positionen:
            rest = p.menge - gutgeschrieben.get(p.id, _NULL)
            if rest > 0:
                auswahl.append((p, rest))
        if not auswahl:
            raise _unverarbeitbar("Es ist nichts mehr gutzuschreiben")
    else:
        nach_id = {p.id: p for p in original_positionen}
        gesehen: set[UUID] = set()
        for wahl in body.positionen or []:
            position = nach_id.get(wahl.position_id)
            if position is None:
                raise _unverarbeitbar(f"Position {wahl.position_id} gehört nicht zu dieser Rechnung")
            if wahl.position_id in gesehen:
                raise _unverarbeitbar(f"Position {position.position} ist mehrfach angegeben")
            gesehen.add(wahl.position_id)
            rest = position.menge - gutgeschrieben.get(position.id, _NULL)
            if wahl.menge > rest:
                raise _unverarbeitbar(
                    f"Position {position.position}: Gutschriftsmenge {wahl.menge:f} übersteigt die noch "
                    f"gutschreibbare Menge {max(rest, _NULL):f}"
                )
            auswahl.append((position, wahl.menge))
        auswahl.sort(key=lambda a: a[0].position)

    rechnungsnummer = await next_rechnungsnummer(session, original.mandant_id)
    jetzt = datetime.now(timezone.utc)
    gutschrift = Rechnung(
        mandant_id=original.mandant_id,
        kunde_id=original.kunde_id,
        vorgang_id=original.vorgang_id,
        rechnungsnummer=rechnungsnummer,
        betrag_netto=_NULL,
        mwst_satz=original.mwst_satz,
        leistungsdatum=original.leistungsdatum,
        status="versendet",
        versendet_am=jetzt,
        erstellt_von=actor_user_id,
        rechnungsart="gutschrift",
        bezug_rechnung_id=original.id,
        gutschrift_grund=body.grund,
    )
    session.add(gutschrift)
    await session.flush()

    neue: list[RechnungPosition] = []
    for nummer, (p, menge) in enumerate(auswahl, start=1):
        if p is None:
            gruppe = steuer_service.steuer_gruppen(original, [])[0]
            steuer = steuer_service.PositionSteuer(
                gruppe.kategorie,
                gruppe.satz,
                "kleinunternehmer_19"
                if gruppe.kategorie == "E" and steuer_service.ist_kleinunternehmer(mandant)
                else None,
                None,
            )
            neue.append(
                _position(
                    gutschrift,
                    nummer,
                    beschreibung=f"Gutschrift zu Rechnung {original.rechnungsnummer}",
                    menge=menge,
                    einheit="psch",
                    einzelpreis=-gruppe.netto,
                    steuer=steuer,
                )
            )
        else:
            steuer = steuer_service.PositionSteuer(
                p.steuer_kategorie, p.steuer_satz, p.steuer_grund, p.steuer_grund_text
            )
            neue.append(
                _position(
                    gutschrift,
                    nummer,
                    beschreibung=p.beschreibung,
                    menge=menge,
                    einheit=p.einheit,
                    einzelpreis=-p.einzelpreis,
                    steuer=steuer,
                    bezug_position_id=p.id,
                    # Nur fuer die Gruppendarstellung der PDF -- quelle/lv/material
                    # bleiben leer, der Beleg ist nie Sperrgrundlage.
                    vorgang_id=p.vorgang_id,
                )
            )
    # Vorab pruefen, bevor etwas geschrieben wird: eine Gutschrift muss den
    # Betrag verringern (die Gutschrift einer reinen Abzugsposition waere
    # eine Belastung).
    gruppen = steuer_service.steuer_gruppen(gutschrift, neue)
    if steuer_service.brutto_summe(gruppen) >= 0:
        raise _unverarbeitbar("Die Gutschrift muss einen negativen Gesamtbetrag ergeben")
    gutschrift.betrag_netto = steuer_service.netto_summe(gruppen)
    for position in neue:
        session.add(position)
    await session.flush()
    await session.refresh(gutschrift)
    return gutschrift


async def gutschrift_summe(session: AsyncSession, rechnung_id: UUID) -> Decimal:
    """Summe der Betraege (positiv) der nicht stornierten Gutschriften."""
    summe = _NULL
    for g in await gutschriften_zu(session, rechnung_id):
        summe += abs(rechnung_service.brutto_betrag(g, await rechnung_service.positionen_fuer(session, g.id)))
    return summe


async def status_nach_gutschriften(
    session: AsyncSession, original: Rechnung, *, bezahlt_am: datetime | None = None
) -> bool:
    """Setzt den Status des Originals nach dem Anlegen bzw. Stornieren einer
    Gutschrift neu: deckt Zahlung + Gutschrift das Brutto, ist die Rechnung
    bezahlt; nimmt eine Stornierung der Gutschrift das wieder zurueck, faellt
    sie auf teilweise_bezahlt/versendet. Gibt zurueck, ob die Rechnung allein
    durch Gutschriften voll gedeckt ist (dann ist nichts abzurechnen)."""
    if original.status not in ("versendet", "teilweise_bezahlt", "bezahlt"):
        return False
    positionen = await rechnung_service.positionen_fuer(session, original.id)
    zahlungen = await rechnung_service.zahlungen_fuer(session, original.id)
    brutto = rechnung_service.brutto_betrag(original, positionen)
    bezahlt = rechnung_service.bezahlter_betrag(zahlungen)
    gutschriften = await gutschrift_summe(session, original.id)
    if brutto - bezahlt - gutschriften <= 0:
        if original.status != "bezahlt":
            original.status = "bezahlt"
            original.bezahlt_am = bezahlt_am or datetime.now(timezone.utc)
    elif bezahlt > 0:
        original.status = "teilweise_bezahlt"
        original.bezahlt_am = None
    else:
        original.status = "versendet"
        original.bezahlt_am = None
    return gutschriften >= brutto


async def pruefe_abzuege_fuer_versand(session: AsyncSession, rechnung: Rechnung) -> list[str]:
    """Die Abschlaege einer Schlussrechnung muessen beim Versand noch
    anrechenbar sein (nicht storniert, nicht anderswo angerechnet) -- zwischen
    Anlage des Entwurfs und Versand kann sich das geaendert haben."""
    positionen = [
        p for p in await rechnung_service.positionen_fuer(session, rechnung.id) if p.abschlag_rechnung_id is not None
    ]
    if not positionen:
        return []
    abschlag_ids = list(dict.fromkeys(p.abschlag_rechnung_id for p in positionen))
    anderswo = await abschlag_angerechnet_in(session, abschlag_ids, ausser_rechnung_id=rechnung.id)
    probleme: list[str] = []
    for abschlag_id in abschlag_ids:
        abschlag = await session.get(Rechnung, abschlag_id)
        if abschlag is None or abschlag.status == "storniert" or abschlag.geloescht_am is not None:
            nummer = abschlag.rechnungsnummer if abschlag else str(abschlag_id)
            probleme.append(f"Der angerechnete Abschlag {nummer} ist storniert oder gelöscht")
        elif abschlag_id in anderswo:
            probleme.append(
                f"Der Abschlag {abschlag.rechnungsnummer} ist bereits in Rechnung "
                f"{anderswo[abschlag_id].rechnungsnummer} angerechnet"
            )
    return probleme


async def vorgang_event_gutschrift(
    session: AsyncSession, original: Rechnung, gutschrift: Rechnung, actor_user_id: UUID
) -> None:
    vorgang_ids = list(
        dict.fromkeys(
            v
            for v in [
                original.vorgang_id,
                *(p.vorgang_id for p in await rechnung_service.positionen_fuer(session, gutschrift.id)),
            ]
            if v is not None
        )
    )
    for vorgang_id in vorgang_ids:
        if await session.get(Vorgang, vorgang_id) is not None:
            session.add(
                VorgangEvent(
                    mandant_id=original.mandant_id,
                    vorgang_id=vorgang_id,
                    event_type="rechnung_status",
                    author_user_id=actor_user_id,
                    body=f"Rechnung {original.rechnungsnummer}: Gutschrift {gutschrift.rechnungsnummer} erstellt",
                    payload={"rechnung_id": str(original.id), "gutschrift_rechnung_id": str(gutschrift.id)},
                )
            )
