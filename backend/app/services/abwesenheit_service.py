"""Abwesenheiten (Urlaub, Krankheit, Freizeitausgleich) und Urlaubskonto
(docs/konzepte/ZEITERFASSUNG.md, Abschnitt "Abwesenheiten, Urlaubskonto,
Freizeitausgleich"). Tageszaehlung und Kontoberechnung sind reine Funktionen;
die DB-Helfer darunter laden nur Soll/Feiertage und schreiben die
automatisch erzeugten Zeiteintraege."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zeit import in_lokal, tagesbeginn_utc, tagesende_utc, zeitzone
from app.models.abwesenheit import Abwesenheitsantrag
from app.models.arbeitszeit import ArbeitszeitSoll, Feiertag
from app.models.zeiterfassung import Zeiterfassung
from app.services.arbeitszeit_service import SollZeileLike, soll_fuer_tag

# Ein Antrag ueber mehr als ein Jahr ist fast sicher ein Tippfehler und wuerde
# die Tageszaehlung unnoetig aufblaehen.
ANTRAG_MAX_TAGE = 366
KALENDER_MAX_TAGE = 366

_EINS = Decimal("1.0")
_HALB = Decimal("0.5")
_NULL_TAGE = Decimal("0.0")

# Beginn des erzeugten Eintrags in lokaler Zeit -- 08:00 liegt auch bei
# Sommerzeit-Umstellung sicher am selben Kalendertag (in_lokal/saldo ordnen
# nach lokalem Starttag zu).
_EINTRAG_BEGINN = time(8, 0)

KATEGORIE_JE_ART = {"urlaub": "urlaub", "krankheit": "krankheit", "freizeitausgleich": "freizeitausgleich"}
TAETIGKEIT_JE_ART = {"urlaub": "Urlaub", "krankheit": "Krankheit", "freizeitausgleich": "Freizeitausgleich"}


@dataclass(frozen=True)
class AbwesenheitsTag:
    datum: date
    faktor: Decimal  # 1.0 ganzer, 0.5 halber Tag
    stunden: Decimal  # Soll des Tages mal Faktor


def abwesenheitstage(
    von: date,
    bis: date,
    halber_tag_von: bool,
    halber_tag_bis: bool,
    soll_zeilen: list[SollZeileLike],
    feiertage: set[date],
) -> list[AbwesenheitsTag]:
    """Arbeitstage des Zeitraums: Soll > 0 und kein Feiertag (soll_fuer_tag
    liefert an Feiertagen 0). Halbe Flags gelten nur fuer den ersten bzw.
    letzten Kalendertag des Antrags, auch wenn der ein freier Tag ist."""
    tage: list[AbwesenheitsTag] = []
    tag = von
    while tag <= bis:
        soll = soll_fuer_tag(tag, soll_zeilen, feiertage)
        if soll > 0:
            halb = (tag == von and halber_tag_von) or (tag == bis and halber_tag_bis)
            faktor = _HALB if halb else _EINS
            tage.append(AbwesenheitsTag(tag, faktor, (soll * faktor).quantize(Decimal("0.01"))))
        tag += timedelta(days=1)
    return tage


def summe_tage(tage: list[AbwesenheitsTag]) -> Decimal:
    return sum((t.faktor for t in tage), _NULL_TAGE)


@dataclass(frozen=True)
class Urlaubskonto:
    anspruch: Decimal
    resturlaub: Decimal
    resturlaub_verfallen: Decimal
    genommen: Decimal
    beantragt: Decimal
    verbleibend: Decimal


def berechne_konto(
    anspruch: Decimal,
    resturlaub: Decimal,
    resturlaub_verfaellt_am: date | None,
    genommen_tage: list[tuple[date, Decimal]],
    beantragt_tage: list[tuple[date, Decimal]],
    heute: date,
) -> Urlaubskonto:
    """Urlaub bis einschliesslich Stichtag verbraucht zuerst den Resturlaub;
    was davon bis zum Stichtag nicht verbraucht wurde, verfaellt. Beantragte
    (offene) Tage zaehlen wie genommene, damit "verbleibend" nichts doppelt
    vergibt. Vor dem Stichtag gilt der Resturlaub noch voll als verfuegbar.
    Ein Ueberziehen wird nicht geklemmt -- verbleibend darf negativ werden."""
    genommen = sum((f for _, f in genommen_tage), _NULL_TAGE)
    beantragt = sum((f for _, f in beantragt_tage), _NULL_TAGE)
    verfallen = _NULL_TAGE
    if resturlaub_verfaellt_am is not None and heute > resturlaub_verfaellt_am:
        bis_stichtag = sum(
            (f for d, f in (*genommen_tage, *beantragt_tage) if d <= resturlaub_verfaellt_am), _NULL_TAGE
        )
        verfallen = max(resturlaub - bis_stichtag, _NULL_TAGE)
    verbleibend = anspruch + resturlaub - verfallen - genommen - beantragt
    return Urlaubskonto(anspruch, resturlaub, verfallen, genommen, beantragt, verbleibend)


def eintrag_zeitraum(tag: date, stunden: Decimal) -> tuple[datetime, datetime]:
    start = datetime.combine(tag, _EINTRAG_BEGINN, tzinfo=zeitzone()).astimezone(timezone.utc)
    return start, start + timedelta(minutes=int(stunden * 60))


# --- DB-Helfer ------------------------------------------------------------


async def soll_und_feiertage_laden(
    session: AsyncSession, user_ids: set[UUID], von: date, bis: date
) -> tuple[dict[UUID, list[ArbeitszeitSoll]], set[date]]:
    soll: dict[UUID, list[ArbeitszeitSoll]] = {uid: [] for uid in user_ids}
    if user_ids:
        zeilen = (
            await session.execute(select(ArbeitszeitSoll).where(ArbeitszeitSoll.user_id.in_(user_ids)))
        ).scalars()
        for z in zeilen:
            soll[z.user_id].append(z)
    feiertage = set(
        (await session.execute(select(Feiertag.datum).where(Feiertag.datum >= von, Feiertag.datum <= bis)))
        .scalars()
        .all()
    )
    return soll, feiertage


async def tage_je_antrag(
    session: AsyncSession, antraege: list[Abwesenheitsantrag]
) -> dict[UUID, list[AbwesenheitsTag]]:
    if not antraege:
        return {}
    soll, feiertage = await soll_und_feiertage_laden(
        session,
        {a.user_id for a in antraege},
        min(a.von for a in antraege),
        max(a.bis for a in antraege),
    )
    return {
        a.id: abwesenheitstage(a.von, a.bis, a.halber_tag_von, a.halber_tag_bis, soll[a.user_id], feiertage)
        for a in antraege
    }


async def hat_ueberschneidung(
    session: AsyncSession, user_id: UUID, von: date, bis: date, *, ausser: UUID | None = None
) -> bool:
    stmt = select(Abwesenheitsantrag.id).where(
        Abwesenheitsantrag.user_id == user_id,
        Abwesenheitsantrag.status.in_(("offen", "genehmigt")),
        Abwesenheitsantrag.von <= bis,
        Abwesenheitsantrag.bis >= von,
    )
    if ausser is not None:
        stmt = stmt.where(Abwesenheitsantrag.id != ausser)
    return (await session.execute(stmt.limit(1))).first() is not None


async def zeiteintraege_erzeugen(
    session: AsyncSession, antrag: Abwesenheitsantrag, tage: list[AbwesenheitsTag]
) -> int:
    """Ein Eintrag je Arbeitstag. Tage, an denen der Mitarbeiter bereits einen
    nicht geloeschten Eintrag derselben Kategorie hat (z. B. von Hand
    nachgetragener Urlaub), werden uebersprungen statt doppelt angelegt."""
    if not tage:
        return 0
    kategorie = KATEGORIE_JE_ART[antrag.art]
    vorhanden = {
        in_lokal(start).date()
        for start in (
            await session.execute(
                select(Zeiterfassung.start_at).where(
                    Zeiterfassung.techniker_id == antrag.user_id,
                    Zeiterfassung.kategorie == kategorie,
                    Zeiterfassung.geloescht_am.is_(None),
                    Zeiterfassung.start_at >= tagesbeginn_utc(tage[0].datum),
                    Zeiterfassung.start_at < tagesende_utc(tage[-1].datum),
                )
            )
        )
        .scalars()
        .all()
    }
    angelegt = 0
    for t in tage:
        if t.datum in vorhanden:
            continue
        start, ende = eintrag_zeitraum(t.datum, t.stunden)
        session.add(
            Zeiterfassung(
                mandant_id=antrag.mandant_id,
                techniker_id=antrag.user_id,
                start_at=start,
                ende_at=ende,
                kategorie=kategorie,
                taetigkeit=TAETIGKEIT_JE_ART[antrag.art] + (" (halber Tag)" if t.faktor < 1 else ""),
                abrechenbar=False,
                quelle="manuell",
                abwesenheit_id=antrag.id,
            )
        )
        angelegt += 1
    await session.flush()
    return angelegt


async def zeiteintraege_entfernen(session: AsyncSession, antrag: Abwesenheitsantrag, durch: UUID) -> None:
    """Papierkorb-Konvention (SoftDeleteMixin): geloescht_am statt DELETE."""
    jetzt = datetime.now(timezone.utc)
    eintraege = (
        await session.execute(
            select(Zeiterfassung).where(
                Zeiterfassung.abwesenheit_id == antrag.id, Zeiterfassung.geloescht_am.is_(None)
            )
        )
    ).scalars()
    for e in eintraege:
        e.geloescht_am = jetzt
        e.geloescht_von = durch
    await session.flush()
