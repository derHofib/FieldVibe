from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import DateTime, Float, String, and_, cast, func, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.zeit import tagesbeginn_utc, tagesende_utc
from app.models.kunde import Kunde
from app.models.projekt import Projekt
from app.models.rechnung import Rechnung
from app.models.telefonat import Telefonat
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.statistik import (
    AggregatAntwort,
    AggregatBereich,
    AggregatGruppierung,
    AggregatKennzahl,
    AggregatZeile,
)
from app.services import rechnung_service

MAX_ZEILEN = 500

KENNZAHLEN: dict[str, tuple[str, ...]] = {
    "vorgaenge": ("anzahl_erstellt", "anzahl_abgeschlossen", "durchlaufzeit_tage", "arbeitszeit_stunden"),
    "rechnungen": ("umsatz_netto", "umsatz_brutto", "anzahl"),
    "telefonate": ("anzahl", "telefonzeit_minuten"),
}
GRUPPIERUNGEN: dict[str, tuple[str, ...]] = {
    "vorgaenge": ("monat", "woche", "techniker", "kunde", "status", "leistungstyp", "prioritaet", "projekt"),
    "rechnungen": ("monat", "kunde", "status"),
    "telefonate": ("monat", "woche", "techniker", "kunde"),
}

_ZEIT_GRUPPIERUNGEN = ("monat", "woche")

_VORGANG_STATUS_LABEL = {
    "neu": "Neu",
    "geplant": "Geplant",
    "in_arbeit": "In Arbeit",
    "wartet_kunde": "Wartet auf Kunde",
    "abgeschlossen": "Abgeschlossen",
    "abgerechnet": "Abgerechnet",
    "storniert": "Storniert",
}
_LEISTUNGSTYP_LABEL = {
    "installation": "Installation",
    "pruefung": "Prüfung",
    "wartung": "Wartung",
    "stoerung": "Störung",
    "beratung": "Beratung",
    "planung": "Planung",
}
_RECHNUNG_STATUS_LABEL = {
    "entwurf": "Entwurf",
    "versendet": "Versendet",
    "teilweise_bezahlt": "Teilweise bezahlt",
    "bezahlt": "Bezahlt",
    "storniert": "Storniert",
}

OHNE_SCHLUESSEL = "ohne"


class UngueltigeAbfrage(Exception):
    """Die Route macht daraus ein 422 mit der deutschen Meldung."""


@dataclass(frozen=True)
class _Abfrage:
    bezug_name: str
    bezug_spalte: object
    wert: object
    from_: object
    bedingungen: list
    # Spalten je Gruppierung, die vom Bereich abhaengen (Techniker bei
    # Arbeitszeit = wer gearbeitet hat, sonst der zugewiesene Techniker).
    techniker_spalte: object | None
    kunde_spalte: object
    status_spalte: object


def pruefe_kombination(bereich: AggregatBereich, kennzahl: AggregatKennzahl, gruppierung: AggregatGruppierung) -> None:
    if kennzahl not in KENNZAHLEN[bereich]:
        raise UngueltigeAbfrage(
            f"Kennzahl '{kennzahl}' passt nicht zum Bereich '{bereich}' (erlaubt: {', '.join(KENNZAHLEN[bereich])})"
        )
    if gruppierung not in GRUPPIERUNGEN[bereich]:
        raise UngueltigeAbfrage(
            f"Gruppierung '{gruppierung}' ist für den Bereich '{bereich}' nicht möglich "
            f"(erlaubt: {', '.join(GRUPPIERUNGEN[bereich])})"
        )


def _lokal(spalte):
    return func.timezone(get_settings().zeitzone, spalte)


def _vorgang_abfrage(
    kennzahl: str,
    techniker_id: UUID | None,
    kunde_id: UUID | None,
    projekt_id: UUID | None,
    status: str | None,
    erlaubte_kunden: set[UUID] | None,
    erlaubte_techniker: set[UUID] | None,
) -> _Abfrage:
    # created_at ist im ORM ohne timezone=True gemappt (DB-Spalte ist timestamptz),
    # tz-aware Vergleichswerte lehnt asyncpg sonst ab.
    erstellt = type_coerce(Vorgang.created_at, DateTime(timezone=True))
    bedingungen = [Vorgang.geloescht_am.is_(None)]
    if kunde_id:
        bedingungen.append(Vorgang.kunde_id == kunde_id)
    if projekt_id:
        bedingungen.append(Vorgang.projekt_id == projekt_id)
    if status:
        bedingungen.append(Vorgang.status == status)
    if erlaubte_kunden is not None:
        bedingungen.append(Vorgang.kunde_id.in_(erlaubte_kunden))

    if kennzahl == "arbeitszeit_stunden":
        # Nur Kategorie "auftrag" (wie der Arbeitszeit-Anteil in /api/zeiterfassung/summen);
        # Fahrzeit ist eine eigene Grosse, Pause/Urlaub etc. haben keinen Vorgang.
        bedingungen += [
            Zeiterfassung.geloescht_am.is_(None),
            Zeiterfassung.kategorie == "auftrag",
            Zeiterfassung.ende_at.is_not(None),
        ]
        if techniker_id:
            bedingungen.append(Zeiterfassung.techniker_id == techniker_id)
        # Personenbezogene Zeiten: wie darf_mitarbeiterdaten_einsehen nur Nutzer im
        # Scope von mitarbeiterverwaltung (None = alle).
        if erlaubte_techniker is not None:
            bedingungen.append(Zeiterfassung.techniker_id.in_(erlaubte_techniker))
        return _Abfrage(
            bezug_name="zeiterfassung_start",
            bezug_spalte=Zeiterfassung.start_at,
            wert=func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at)) / 3600.0,
            from_=Zeiterfassung.__table__.join(Vorgang.__table__, Vorgang.id == Zeiterfassung.vorgang_id),
            bedingungen=bedingungen,
            techniker_spalte=Zeiterfassung.techniker_id,
            kunde_spalte=Vorgang.kunde_id,
            status_spalte=Vorgang.status,
        )

    if techniker_id:
        bedingungen.append(Vorgang.zugewiesener_user_id == techniker_id)

    if kennzahl == "anzahl_erstellt":
        bezug_name, bezug, wert = "erstellt_am", erstellt, func.count()
    elif kennzahl == "anzahl_abgeschlossen":
        bezug_name, bezug, wert = "abgeschlossen_am", Vorgang.abgeschlossen_am, func.count()
        bedingungen.append(Vorgang.abgeschlossen_am.is_not(None))
    else:
        # Abschluss vor Anlage (Altdaten) wuerde den Schnitt ins Negative ziehen,
        # wie in vorgang_kennzahlen: solche Datensaetze zaehlen hier gar nicht.
        bezug_name, bezug = "abgeschlossen_am", Vorgang.abgeschlossen_am
        wert = func.avg(func.extract("epoch", Vorgang.abgeschlossen_am - Vorgang.created_at)) / 86400.0
        bedingungen += [Vorgang.abgeschlossen_am.is_not(None), Vorgang.abgeschlossen_am >= Vorgang.created_at]
    return _Abfrage(
        bezug_name=bezug_name,
        bezug_spalte=bezug,
        wert=wert,
        from_=Vorgang.__table__,
        bedingungen=bedingungen,
        techniker_spalte=Vorgang.zugewiesener_user_id,
        kunde_spalte=Vorgang.kunde_id,
        status_spalte=Vorgang.status,
    )


def _rechnung_abfrage(kennzahl: str, kunde_id: UUID | None) -> _Abfrage:
    # Bezug und Regeln wie ust_va_bericht: Entwuerfe haben kein versendet_am und
    # zaehlen nie. Storno-Belege (negative Positionen) und Gutschriften (negativ)
    # gehen in die Umsatzsummen ein, die stornierte Original-Rechnung bleibt
    # drin -- beides hebt sich zu null auf, wie in der UStVA. Fuer "anzahl" waere
    # dasselbe irrefuehrend (Original + Storno = 2 statt 0 Rechnungen), daher
    # zaehlen dort nur echte, nicht stornierte Rechnungen.
    bedingungen = [Rechnung.geloescht_am.is_(None), Rechnung.versendet_am.is_not(None)]
    if kunde_id:
        bedingungen.append(Rechnung.kunde_id == kunde_id)
    if kennzahl == "umsatz_netto":
        wert = func.sum(rechnung_service.netto_sql(Rechnung))
    elif kennzahl == "umsatz_brutto":
        wert = func.sum(rechnung_service.brutto_sql(Rechnung))
    else:
        wert = func.count()
        bedingungen += [
            Rechnung.ist_storno.is_(False),
            Rechnung.rechnungsart != "gutschrift",
            Rechnung.status != "storniert",
        ]
    return _Abfrage(
        bezug_name="versendet_am",
        bezug_spalte=Rechnung.versendet_am,
        wert=wert,
        from_=Rechnung.__table__,
        bedingungen=bedingungen,
        techniker_spalte=None,
        kunde_spalte=Rechnung.kunde_id,
        status_spalte=Rechnung.status,
    )


def _telefonat_abfrage(
    kennzahl: str, techniker_id: UUID | None, kunde_id: UUID | None,
    erlaubte_kunden: set[UUID] | None, erlaubte_techniker: set[UUID] | None,
) -> _Abfrage:
    bedingungen = [Telefonat.geloescht_am.is_(None)]
    if kunde_id:
        bedingungen.append(Telefonat.kunde_id == kunde_id)
    if techniker_id:
        bedingungen.append(Telefonat.erfasst_von == techniker_id)
    if erlaubte_kunden is not None:
        bedingungen.append(Telefonat.kunde_id.in_(erlaubte_kunden))
    # Telefonzeit je Person ist wie die Arbeitszeit personenbezogen: nur Erfasser im Scope von mitarbeiterverwaltung.
    if erlaubte_techniker is not None:
        bedingungen.append(Telefonat.erfasst_von.in_(erlaubte_techniker))
    wert = func.count() if kennzahl == "anzahl" else func.coalesce(func.sum(Telefonat.dauer_sekunden), 0) / 60.0
    return _Abfrage(
        bezug_name="beginn",
        bezug_spalte=Telefonat.beginn,
        wert=wert,
        from_=Telefonat.__table__,
        bedingungen=bedingungen,
        techniker_spalte=Telefonat.erfasst_von,
        kunde_spalte=Telefonat.kunde_id,
        status_spalte=None,
    )


def _label_zeit(gruppierung: str, schluessel: str) -> str:
    if gruppierung == "woche":
        jahr, _, woche = schluessel.partition("-W")
        return f"KW {int(woche)}/{jahr}"
    return schluessel


async def aggregat_berechnen(
    session: AsyncSession,
    *,
    bereich: AggregatBereich,
    kennzahl: AggregatKennzahl,
    gruppierung: AggregatGruppierung,
    von: date,
    bis: date,
    techniker_id: UUID | None,
    kunde_id: UUID | None,
    projekt_id: UUID | None,
    status: str | None,
    erlaubte_kunden: set[UUID] | None,
    erlaubte_techniker: set[UUID] | None,
) -> AggregatAntwort:
    pruefe_kombination(bereich, kennzahl, gruppierung)
    if bereich == "rechnungen":
        if techniker_id or projekt_id or status:
            raise UngueltigeAbfrage("Für den Bereich 'rechnungen' ist nur der Filter 'kunde_id' möglich")
        abfrage = _rechnung_abfrage(kennzahl, kunde_id)
        wertbar_status = _RECHNUNG_STATUS_LABEL
    elif bereich == "telefonate":
        if projekt_id or status:
            raise UngueltigeAbfrage("Für den Bereich 'telefonate' sind nur die Filter 'kunde_id' und 'techniker_id' möglich")
        abfrage = _telefonat_abfrage(kennzahl, techniker_id, kunde_id, erlaubte_kunden, erlaubte_techniker)
        wertbar_status = {}
    else:
        abfrage = _vorgang_abfrage(
            kennzahl, techniker_id, kunde_id, projekt_id, status, erlaubte_kunden, erlaubte_techniker
        )
        wertbar_status = _VORGANG_STATUS_LABEL

    bezug = abfrage.bezug_spalte
    bedingungen = [
        *abfrage.bedingungen,
        bezug >= tagesbeginn_utc(von),
        bezug < tagesende_utc(bis),
    ]
    if bereich == "rechnungen" and erlaubte_kunden is not None:
        # Wird in der Route vorher mit 403 abgewiesen; hier nur Absicherung.
        bedingungen.append(Rechnung.kunde_id.in_(erlaubte_kunden))

    wert_spalte = cast(abfrage.wert, Float)

    gesamt_stmt = select(wert_spalte).select_from(abfrage.from_).where(and_(*bedingungen))
    gesamt = (await session.execute(gesamt_stmt)).scalar_one_or_none() or 0.0

    from_ = abfrage.from_
    if gruppierung == "monat":
        schluessel = func.to_char(_lokal(bezug), "YYYY-MM")
        label = schluessel
    elif gruppierung == "woche":
        schluessel = func.to_char(_lokal(bezug), 'IYYY-"W"IW')
        label = schluessel
    elif gruppierung == "techniker":
        schluessel = cast(abfrage.techniker_spalte, String)
        from_ = from_.outerjoin(User.__table__, User.id == abfrage.techniker_spalte)
        label = User.name
    elif gruppierung == "kunde":
        schluessel = cast(abfrage.kunde_spalte, String)
        from_ = from_.join(Kunde.__table__, Kunde.id == abfrage.kunde_spalte)
        label = Kunde.name
    elif gruppierung == "projekt":
        schluessel = cast(Vorgang.projekt_id, String)
        from_ = from_.outerjoin(Projekt.__table__, Projekt.id == Vorgang.projekt_id)
        label = Projekt.name
    elif gruppierung == "status":
        schluessel = label = abfrage.status_spalte
    elif gruppierung == "leistungstyp":
        schluessel = label = Vorgang.leistungstyp
    else:
        schluessel = cast(Vorgang.prioritaet, String)
        label = schluessel

    stmt = (
        select(schluessel.label("schluessel"), label.label("label"), wert_spalte.label("wert"))
        .select_from(from_)
        .where(and_(*bedingungen))
        .group_by(schluessel, label)
    )
    if gruppierung in _ZEIT_GRUPPIERUNGEN:
        stmt = stmt.order_by(schluessel.asc())
    else:
        stmt = stmt.order_by(wert_spalte.desc(), schluessel.asc())
    zeilen_roh = (await session.execute(stmt.limit(MAX_ZEILEN + 1))).all()

    zeilen = []
    for roh_schluessel, roh_label, roh_wert in zeilen_roh[:MAX_ZEILEN]:
        if gruppierung in _ZEIT_GRUPPIERUNGEN:
            schluessel_text, label_text = roh_schluessel, _label_zeit(gruppierung, roh_schluessel)
        elif gruppierung == "status":
            schluessel_text, label_text = roh_schluessel, wertbar_status.get(roh_schluessel, roh_schluessel)
        elif gruppierung == "leistungstyp":
            schluessel_text, label_text = roh_schluessel, _LEISTUNGSTYP_LABEL.get(roh_schluessel, roh_schluessel)
        elif gruppierung == "prioritaet":
            schluessel_text, label_text = roh_schluessel, f"Priorität {roh_schluessel}"
        elif roh_schluessel is None:
            fehlt = "Nicht zugewiesen" if gruppierung == "techniker" else "Ohne Projekt"
            schluessel_text, label_text = OHNE_SCHLUESSEL, fehlt
        else:
            schluessel_text, label_text = roh_schluessel, roh_label or roh_schluessel
        zeilen.append(AggregatZeile(schluessel=schluessel_text, label=label_text, wert=round(float(roh_wert or 0.0), 2)))

    return AggregatAntwort(
        bereich=bereich,
        kennzahl=kennzahl,
        gruppierung=gruppierung,
        von=von,
        bis=bis,
        datumsbezug=abfrage.bezug_name,
        zeilen=zeilen,
        gesamt=round(float(gesamt), 2),
        abgeschnitten=len(zeilen_roh) > MAX_ZEILEN,
    )
