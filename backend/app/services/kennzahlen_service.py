"""Kennzahlen-Katalog und -Daten fuer die Dashboards (Konzept kennzahlen-dashboards).

Jede Kennzahl liefert dieselbe Datenform (Gesamtwert, optional Vorperiode, optional
Zeilen je Aufteilung); die Darstellung waehlt das Frontend. Zeitraum-Kennzahlen
rechnen ueber aggregat_berechnen bzw. eine eigene Abfrage, Stand-Kennzahlen sind
Momentaufnahmen von heute und ignorieren von/bis.
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import Float, String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_module, require_recht
from app.core.config import get_settings
from app.core.zeit import tagesbeginn_utc, tagesende_utc, zeitzone
from app.models.angebot import Angebot
from app.models.kunde import Kunde
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.kennzahlen import (
    KennzahlArt,
    KennzahlDaten,
    KennzahlDef,
    KennzahlEinheit,
    KennzahlGruppierung,
    KennzahlZeile,
)
from app.services import auswertung_service
from app.services.date_utils import add_months
from app.services.statistik_aggregat_service import (
    _LEISTUNGSTYP_LABEL,
    _VORGANG_STATUS_LABEL,
    GRUPPIERUNGEN,
    OHNE_SCHLUESSEL,
    aggregat_berechnen,
)
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import erlaubte_kunde_ids, erlaubte_user_ids

MAX_ZEILEN = 50

_GRUPPIERUNG_LABEL = {
    "monat": "Monat",
    "woche": "Woche",
    "techniker": "Techniker",
    "kunde": "Kunde",
    "status": "Status",
    "leistungstyp": "Leistungstyp",
    "prioritaet": "Priorität",
    "projekt": "Projekt",
    "alter": "Alter",
    "lieferant": "Lieferant",
}
_ZEIT_GRUPPIERUNGEN = ("monat", "woche")
_MONATE_KURZ = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")

_VORGANG_GRUPPIERUNGEN = ("monat", "woche", "techniker", "kunde", "status", "leistungstyp", "prioritaet", "projekt")


class UnbekannteKennzahl(Exception):
    pass


class KeinRecht(Exception):
    pass


class UngueltigeAnfrage(Exception):
    """Die Route macht daraus ein 422 mit der deutschen Meldung."""


@dataclass
class _Roh:
    gesamt: float | None
    # (schluessel, label, wert); bei Zeit-Aufteilung nur Buckets mit Daten, die Luecken fuellt kennzahl_daten.
    zeilen: list[tuple[str, str, float | None]]
    abgeschnitten: bool = False
    datumsbezug: str | None = None


_Berechne = Callable[[AsyncSession, AuthContext, str, date | None, date | None], Awaitable[_Roh]]


@dataclass(frozen=True)
class _Kennzahl:
    definition: KennzahlDef
    # None = nur statistik.sehen (vom Router geprueft); "finanzen" = zusaetzlich Modul abrechnung,
    # abrechnung.sehen und keine Kundeneinschraenkung (wie /api/auswertung).
    recht: str | None
    berechne: _Berechne


def _heute() -> date:
    return datetime.now(zeitzone()).date()


def _lokal(spalte):
    return func.timezone(get_settings().zeitzone, spalte)


async def _finanzen_erlaubt(session: AsyncSession, auth: AuthContext) -> bool:
    # Dieselben Sperren wie /api/auswertung und der Rechnungs-Bereich von /api/statistik/aggregat.
    try:
        await require_module("abrechnung")(auth, session)
        await require_recht("abrechnung", "sehen")(auth, session)
    except HTTPException:
        return False
    return await erlaubte_kunde_ids(session, auth) is None


def _gruppierungen(*schluessel: str) -> list[KennzahlGruppierung]:
    return [
        KennzahlGruppierung(schluessel=s, label=_GRUPPIERUNG_LABEL[s], zeit=s in _ZEIT_GRUPPIERUNGEN)
        for s in schluessel
    ]


def _def(
    schluessel: str, titel: str, beschreibung: str, einheit: KennzahlEinheit, art: KennzahlArt,
    summierbar: bool, gruppierungen: tuple[str, ...],
) -> KennzahlDef:
    return KennzahlDef(
        schluessel=schluessel, titel=titel, beschreibung=beschreibung,
        bereich=schluessel.split(".")[0],  # type: ignore[arg-type]
        einheit=einheit, art=art, summierbar=summierbar, gruppierungen=_gruppierungen(*gruppierungen),
    )


def _kategorie_label(gruppierung: str, roh_schluessel: str | None, roh_label: str | None) -> tuple[str, str]:
    if roh_schluessel is None:
        return OHNE_SCHLUESSEL, "Nicht zugewiesen" if gruppierung == "techniker" else "Ohne Projekt"
    if gruppierung == "status":
        return roh_schluessel, _VORGANG_STATUS_LABEL.get(roh_schluessel, roh_schluessel)
    if gruppierung == "leistungstyp":
        return roh_schluessel, _LEISTUNGSTYP_LABEL.get(roh_schluessel, roh_schluessel)
    if gruppierung == "prioritaet":
        return roh_schluessel, f"Priorität {roh_schluessel}"
    return roh_schluessel, roh_label or roh_schluessel


def _zeit_label(gruppierung: str, schluessel: str) -> str:
    if gruppierung == "woche":
        return f"KW {int(schluessel.partition('-W')[2])}"
    jahr, _, monat = schluessel.partition("-")
    return f"{_MONATE_KURZ[int(monat) - 1]} {jahr}"


def _zeit_buckets(gruppierung: str, von: date, bis: date) -> list[tuple[str, str]]:
    """Alle Buckets zwischen von und bis (Schluessel wie in aggregat_berechnen), damit Zeitreihen lueckenlos sind."""
    gesehen: dict[str, str] = {}
    tag = von
    while tag <= bis:
        if gruppierung == "woche":
            iso = tag.isocalendar()
            schluessel = f"{iso.year}-W{iso.week:02d}"
        else:
            schluessel = f"{tag.year}-{tag.month:02d}"
        gesehen.setdefault(schluessel, _zeit_label(gruppierung, schluessel))
        tag += timedelta(days=1)
    return list(gesehen.items())


# --- Zeitraum-Kennzahlen ueber aggregat_berechnen -----------------------------------------------------------------

def _aggregat(bereich: str, kennzahl: str, summierbar: bool) -> _Berechne:
    async def berechne(session, auth, gruppierung, von, bis) -> _Roh:
        erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
        erlaubte_techniker = (
            await erlaubte_user_ids(session, auth, "mitarbeiterverwaltung", "bearbeiten")
            if bereich == "telefonate"
            else None
        )
        # "gesamt" gibt es im Aggregat nicht; der Gesamtwert steht in jeder Antwort, die Zeilen werden dann verworfen.
        antwort = await aggregat_berechnen(
            session,
            bereich=bereich,  # type: ignore[arg-type]
            kennzahl=kennzahl,  # type: ignore[arg-type]
            gruppierung=GRUPPIERUNGEN[bereich][0] if gruppierung == "gesamt" else gruppierung,  # type: ignore[arg-type]
            von=von, bis=bis, techniker_id=None, kunde_id=None, projekt_id=None, status=None,
            erlaubte_kunden=erlaubte_kunden, erlaubte_techniker=erlaubte_techniker,
        )
        # Ein Durchschnitt ueber nichts ist "keine Daten", nicht 0.
        gesamt: float | None = antwort.gesamt if (summierbar or antwort.zeilen) else None
        if gruppierung == "gesamt":
            return _Roh(gesamt, [], False, antwort.datumsbezug)
        zeilen = [(z.schluessel, z.label, z.wert) for z in antwort.zeilen]
        return _Roh(gesamt, zeilen, antwort.abgeschnitten, antwort.datumsbezug)

    return berechne


# --- Zeitraum-Kennzahlen Angebote ---------------------------------------------------------------------------------

def _angebote(art: str) -> _Berechne:
    async def berechne(session, auth, gruppierung, von, bis) -> _Roh:
        bezug = Angebot.angenommen_am if art == "angenommen" else Angebot.versendet_am
        bedingungen = [
            Angebot.geloescht_am.is_(None),
            bezug >= tagesbeginn_utc(von),
            bezug < tagesende_utc(bis),
        ]
        if art == "quote":
            # nullif: ohne versendete Angebote keine Quote statt Division durch 0
            wert = cast(
                100.0 * func.count().filter(Angebot.status == "angenommen") / func.nullif(func.count(), 0), Float
            )
        else:
            wert = cast(func.count(), Float)

        gesamt_roh = (await session.execute(select(wert).where(and_(*bedingungen)))).scalar_one_or_none()
        gesamt = None if gesamt_roh is None else round(float(gesamt_roh), 2)
        if gruppierung == "gesamt":
            return _Roh(gesamt, [], False, "angenommen_am" if art == "angenommen" else "versendet_am")

        from_ = Angebot.__table__
        if gruppierung == "monat":
            schluessel = label = func.to_char(_lokal(bezug), "YYYY-MM")
        elif gruppierung == "woche":
            schluessel = label = func.to_char(_lokal(bezug), 'IYYY-"W"IW')
        else:
            schluessel = cast(Angebot.kunde_id, String)
            from_ = from_.join(Kunde.__table__, Kunde.id == Angebot.kunde_id)
            label = Kunde.name
        stmt = (
            select(schluessel.label("schluessel"), label.label("label"), wert.label("wert"))
            .select_from(from_)
            .where(and_(*bedingungen))
            .group_by(schluessel, label)
            .order_by(wert.desc().nulls_last(), schluessel.asc())
        )
        roh = (await session.execute(stmt)).all()
        zeilen = [
            (s, _zeit_label(gruppierung, s) if gruppierung in _ZEIT_GRUPPIERUNGEN else (lbl or s),
             None if w is None else round(float(w), 2))
            for s, lbl, w in roh
        ]
        return _Roh(gesamt, zeilen, False, "angenommen_am" if art == "angenommen" else "versendet_am")

    return berechne


# --- Stand-Kennzahlen Vorgaenge -----------------------------------------------------------------------------------

def _vorgaenge_stand(nur_ueberfaellig: bool) -> _Berechne:
    async def berechne(session, auth, gruppierung, von, bis) -> _Roh:
        bedingungen = [Vorgang.geloescht_am.is_(None), Vorgang.status.notin_(VORGANG_STATUS_GESCHLOSSEN)]
        if nur_ueberfaellig:
            # Wie der "dringend"-Zaehler der Office-Seitenleiste: Faelligkeit vor dem lokalen heutigen Tag.
            bedingungen.append(Vorgang.faelligkeit_am < tagesbeginn_utc(_heute()))
        erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
        if erlaubte_kunden is not None:
            bedingungen.append(Vorgang.kunde_id.in_(erlaubte_kunden))

        wert = cast(func.count(), Float)
        gesamt = float((await session.execute(select(wert).where(and_(*bedingungen)))).scalar_one())
        if gruppierung == "gesamt":
            return _Roh(round(gesamt, 2), [])

        from_ = Vorgang.__table__
        if gruppierung == "techniker":
            schluessel = cast(Vorgang.zugewiesener_user_id, String)
            from_ = from_.outerjoin(User.__table__, User.id == Vorgang.zugewiesener_user_id)
            label = User.name
        elif gruppierung == "kunde":
            schluessel = cast(Vorgang.kunde_id, String)
            from_ = from_.join(Kunde.__table__, Kunde.id == Vorgang.kunde_id)
            label = Kunde.name
        elif gruppierung == "status":
            schluessel = label = Vorgang.status
        elif gruppierung == "leistungstyp":
            schluessel = label = Vorgang.leistungstyp
        else:
            schluessel = cast(Vorgang.prioritaet, String)
            label = schluessel
        stmt = (
            select(schluessel.label("schluessel"), label.label("label"), wert.label("wert"))
            .select_from(from_)
            .where(and_(*bedingungen))
            .group_by(schluessel, label)
            .order_by(wert.desc(), schluessel.asc())
        )
        zeilen = []
        for roh_schluessel, roh_label, roh_wert in (await session.execute(stmt)).all():
            s, lbl = _kategorie_label(gruppierung, roh_schluessel, roh_label)
            zeilen.append((s, lbl, round(float(roh_wert), 2)))
        return _Roh(round(gesamt, 2), zeilen)

    return berechne


# --- Stand-Kennzahlen Finanzen (offene Posten) --------------------------------------------------------------------

def _offene_posten(seite: str, nur_ueberfaellig: bool) -> _Berechne:
    async def berechne(session, auth, gruppierung, von, bis) -> _Roh:
        bericht = await auswertung_service.offene_posten_bericht(session, auth.mandant_id, _heute())
        eintraege = bericht.debitoren if seite == "debitoren" else bericht.kreditoren
        if nur_ueberfaellig:
            eintraege = [e for e in eintraege if e.tage_ueberfaellig > 0]
        gesamt = round(float(sum(e.offener_betrag for e in eintraege)), 2)
        if gruppierung == "gesamt":
            return _Roh(gesamt, [])

        if gruppierung == "alter":
            # Feste Reihenfolge, leere Altersstufen mit 0 -- sonst springt die Balkenreihe je nach Datenlage.
            summen = {label: 0.0 for label in auswertung_service._BUCKET_REIHENFOLGE}
            for e in eintraege:
                summen[auswertung_service._bucket_label(e.tage_ueberfaellig)] += float(e.offener_betrag)
            zeilen = [(label, label, round(summe, 2)) for label, summe in summen.items()]
            return _Roh(gesamt, zeilen)

        # kunde/lieferant: der Bericht liefert nur den Namen, keine Partner-Id -- Name ist Schluessel und Label.
        je_partner: dict[str, float] = {}
        for e in eintraege:
            je_partner[e.partner_name] = je_partner.get(e.partner_name, 0.0) + float(e.offener_betrag)
        zeilen = [(name, name, round(summe, 2)) for name, summe in je_partner.items()]
        return _Roh(gesamt, zeilen)

    return berechne


KENNZAHLEN: dict[str, _Kennzahl] = {
    k.definition.schluessel: k
    for k in [
        _Kennzahl(
            _def("vorgaenge.erstellt", "Vorgänge erstellt", "Neu angelegte Vorgänge im Zeitraum.",
                 "anzahl", "zeitraum", True, _VORGANG_GRUPPIERUNGEN),
            None, _aggregat("vorgaenge", "anzahl_erstellt", True),
        ),
        _Kennzahl(
            _def("vorgaenge.abgeschlossen", "Vorgänge abgeschlossen", "Im Zeitraum abgeschlossene Vorgänge.",
                 "anzahl", "zeitraum", True, _VORGANG_GRUPPIERUNGEN),
            None, _aggregat("vorgaenge", "anzahl_abgeschlossen", True),
        ),
        _Kennzahl(
            _def("vorgaenge.durchlaufzeit", "Durchlaufzeit",
                 "Durchschnittliche Tage von der Anlage bis zum Abschluss (Abschluss im Zeitraum).",
                 "tage", "zeitraum", False, _VORGANG_GRUPPIERUNGEN),
            None, _aggregat("vorgaenge", "durchlaufzeit_tage", False),
        ),
        _Kennzahl(
            _def("vorgaenge.offen", "Offene Vorgänge", "Alle noch nicht abgeschlossenen Vorgänge (Stand heute).",
                 "anzahl", "stand", True, ("status", "techniker", "kunde", "leistungstyp", "prioritaet")),
            None, _vorgaenge_stand(False),
        ),
        _Kennzahl(
            _def("vorgaenge.ueberfaellig", "Überfällige Vorgänge",
                 "Offene Vorgänge mit Fälligkeit vor heute (Stand heute).",
                 "anzahl", "stand", True, ("techniker", "kunde", "leistungstyp")),
            None, _vorgaenge_stand(True),
        ),
        _Kennzahl(
            _def("finanzen.umsatz_netto", "Umsatz netto", "Netto-Umsatz der versendeten Rechnungen im Zeitraum.",
                 "eur", "zeitraum", True, ("monat", "kunde", "status")),
            "finanzen", _aggregat("rechnungen", "umsatz_netto", True),
        ),
        _Kennzahl(
            _def("finanzen.rechnungen", "Rechnungen", "Anzahl der versendeten Rechnungen im Zeitraum.",
                 "anzahl", "zeitraum", True, ("monat", "kunde", "status")),
            "finanzen", _aggregat("rechnungen", "anzahl", True),
        ),
        _Kennzahl(
            _def("finanzen.offene_forderungen", "Offene Forderungen",
                 "Summe der offenen Posten gegenüber Kunden (Stand heute).",
                 "eur", "stand", True, ("kunde", "alter")),
            "finanzen", _offene_posten("debitoren", False),
        ),
        _Kennzahl(
            _def("finanzen.ueberfaellig", "Überfällige Forderungen",
                 "Offene Posten gegenüber Kunden mit überschrittenem Zahlungsziel (Stand heute).",
                 "eur", "stand", True, ("kunde", "alter")),
            "finanzen", _offene_posten("debitoren", True),
        ),
        _Kennzahl(
            _def("finanzen.verbindlichkeiten", "Verbindlichkeiten",
                 "Summe offener Eingangsrechnungen bei Lieferanten (Stand heute).",
                 "eur", "stand", True, ("lieferant", "alter")),
            "finanzen", _offene_posten("kreditoren", False),
        ),
        _Kennzahl(
            _def("sales.angebote_versendet", "Angebote versendet", "Im Zeitraum versendete Angebote.",
                 "anzahl", "zeitraum", True, ("monat", "woche", "kunde")),
            "finanzen", _angebote("versendet"),
        ),
        _Kennzahl(
            _def("sales.angebote_angenommen", "Angebote angenommen", "Im Zeitraum angenommene Angebote.",
                 "anzahl", "zeitraum", True, ("monat", "woche", "kunde")),
            "finanzen", _angebote("angenommen"),
        ),
        _Kennzahl(
            _def("sales.angebotsquote", "Angebotsquote",
                 "Anteil angenommener Angebote an den im Zeitraum versendeten.",
                 "prozent", "zeitraum", False, ("monat", "woche")),
            "finanzen", _angebote("quote"),
        ),
        _Kennzahl(
            _def("telefonate.anzahl", "Telefonate", "Erfasste Telefonate im Zeitraum.",
                 "anzahl", "zeitraum", True, ("monat", "woche", "techniker", "kunde")),
            None, _aggregat("telefonate", "anzahl", True),
        ),
        _Kennzahl(
            _def("telefonate.dauer", "Telefonzeit", "Gesprächsdauer der erfassten Telefonate im Zeitraum.",
                 "minuten", "zeitraum", True, ("monat", "woche", "techniker", "kunde")),
            None, _aggregat("telefonate", "telefonzeit_minuten", True),
        ),
    ]
}
# Altersstufen haben eine fachliche Reihenfolge statt "groesster Wert zuerst".
_FESTE_REIHENFOLGE_GRUPPIERUNGEN = ("alter",)


async def katalog_fuer(session: AsyncSession, auth: AuthContext) -> list[KennzahlDef]:
    finanzen = await _finanzen_erlaubt(session, auth)
    return [k.definition for k in KENNZAHLEN.values() if k.recht is None or finanzen]


def _runden(wert: float | None) -> float | None:
    return None if wert is None else round(float(wert), 2)


def _zeilen_aufbereiten(
    kz: _Kennzahl, gruppierung: str, roh: _Roh, von: date | None, bis: date | None
) -> tuple[list[tuple[str, str, float | None]], bool]:
    summierbar = kz.definition.summierbar
    if gruppierung in _ZEIT_GRUPPIERUNGEN:
        vorhanden = {s: w for s, _, w in roh.zeilen}
        fehlend = 0.0 if summierbar else None
        return [(s, lbl, vorhanden.get(s, fehlend)) for s, lbl in _zeit_buckets(gruppierung, von, bis)], False
    zeilen = list(roh.zeilen)
    if gruppierung not in _FESTE_REIHENFOLGE_GRUPPIERUNGEN:
        zeilen.sort(key=lambda z: (z[2] is None, -(z[2] or 0.0), z[0]))
    return zeilen[:MAX_ZEILEN], roh.abgeschnitten or len(zeilen) > MAX_ZEILEN


async def kennzahl_daten(
    session: AsyncSession,
    auth: AuthContext,
    schluessel: str,
    gruppierung: str,
    von: date | None,
    bis: date | None,
    vergleich_von: date | None,
    vergleich_bis: date | None,
) -> KennzahlDaten:
    kz = KENNZAHLEN.get(schluessel)
    if kz is None:
        raise UnbekannteKennzahl(f"Unbekannte Kennzahl '{schluessel}'")
    if kz.recht == "finanzen" and not await _finanzen_erlaubt(session, auth):
        raise KeinRecht("Keine Berechtigung für diese Kennzahl")
    erlaubt = [g.schluessel for g in kz.definition.gruppierungen]
    if gruppierung != "gesamt" and gruppierung not in erlaubt:
        raise UngueltigeAnfrage(
            f"Gruppierung '{gruppierung}' ist für '{schluessel}' nicht möglich (erlaubt: gesamt, {', '.join(erlaubt)})"
        )

    ist_stand = kz.definition.art == "stand"
    if not ist_stand:
        for name, a, b in (("", von, bis), ("vergleich_", vergleich_von, vergleich_bis)):
            if name and a is None and b is None:
                continue
            if a is None or b is None:
                raise UngueltigeAnfrage(f"'{name}von' und '{name}bis' müssen gemeinsam angegeben werden")
            if b < a:
                raise UngueltigeAnfrage(f"'{name}bis' darf nicht vor '{name}von' liegen")
            if b > add_months(a, 36):
                raise UngueltigeAnfrage("Der Zeitraum darf höchstens 3 Jahre umfassen")

    roh = await kz.berechne(session, auth, gruppierung, von, bis)
    if ist_stand:
        zeilen, abgeschnitten = _zeilen_aufbereiten(kz, gruppierung, roh, None, None)
        return KennzahlDaten(
            kennzahl=schluessel, einheit=kz.definition.einheit, art="stand", gruppierung=gruppierung,
            von=None, bis=None, gesamt=_runden(roh.gesamt), vorperiode_gesamt=None,
            zeilen=[KennzahlZeile(schluessel=s, label=lbl, wert=_runden(w)) for s, lbl, w in zeilen],
            abgeschnitten=abgeschnitten, datumsbezug=None,
        )

    zeilen, abgeschnitten = _zeilen_aufbereiten(kz, gruppierung, roh, von, bis)
    vorperiode: list[float | None] | dict[str, float | None] | None = None
    vorperiode_gesamt: float | None = None
    if vergleich_von is not None and vergleich_bis is not None:
        vroh = await kz.berechne(session, auth, gruppierung, vergleich_von, vergleich_bis)
        vorperiode_gesamt = _runden(vroh.gesamt)
        if gruppierung != "gesamt":
            vzeilen, _ = _zeilen_aufbereiten(kz, gruppierung, vroh, vergleich_von, vergleich_bis)
            if gruppierung in _ZEIT_GRUPPIERUNGEN:
                # Der n-te Bucket der Vorperiode steht dem n-ten des Zeitraums gegenueber (Schluessel sind verschieden).
                vorperiode = [w for _, _, w in vzeilen]
            else:
                vorperiode = {s: w for s, _, w in vzeilen}

    fehlend_vorher = 0.0 if kz.definition.summierbar else None
    ausgabe = []
    for index, (s, lbl, w) in enumerate(zeilen):
        if vorperiode is None:
            vor = None
        elif isinstance(vorperiode, list):
            vor = _runden(vorperiode[index]) if index < len(vorperiode) else None
        else:
            vor = _runden(vorperiode.get(s, fehlend_vorher))
        ausgabe.append(KennzahlZeile(schluessel=s, label=lbl, wert=_runden(w), vorperiode=vor))

    return KennzahlDaten(
        kennzahl=schluessel, einheit=kz.definition.einheit, art="zeitraum", gruppierung=gruppierung,
        von=von, bis=bis, gesamt=_runden(roh.gesamt), vorperiode_gesamt=vorperiode_gesamt,
        zeilen=ausgabe, abgeschnitten=abgeschnitten, datumsbezug=roh.datumsbezug,
    )
