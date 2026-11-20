"""Rechnungsempfaenger, "Ihr Zeichen" und Leistungsort fuer Rechnungen/Angebote. Die Werte werden beim Anlegen
als Snapshot kopiert (GoBD: eine versendete Rechnung darf sich nicht aendern) und sind nur im Entwurf aenderbar."""
import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auftrag import Auftrag
from app.models.kunde import Kunde
from app.models.projekt import Projekt
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.schemas.kunde_kurz import KundeKurz

LEISTUNGSORT_FELDER = ("bezeichnung", "strasse", "plz", "ort", "land")


def _norm(wert: object) -> str:
    return re.sub(r"[^0-9a-zäöüß]+", "", str(wert or "").lower())


def _adresse_gleich(a: dict | None, b: dict | None) -> bool:
    return all(_norm((a or {}).get(k)) == _norm((b or {}).get(k)) for k in ("strasse", "plz", "ort"))


def leistungsort_bereinigen(wert: dict | None) -> dict | None:
    """Nur bekannte Felder, getrimmt; ohne jeden Inhalt wird daraus None."""
    if not wert:
        return None
    bereinigt = {k: str(wert[k]).strip() for k in LEISTUNGSORT_FELDER if wert.get(k) and str(wert[k]).strip()}
    return bereinigt or None


async def _auftrag_und_projekt(session: AsyncSession, vorgang: Vorgang) -> tuple[Auftrag | None, Projekt | None]:
    auftrag = await session.get(Auftrag, vorgang.auftrag_id) if vorgang.auftrag_id else None
    projekt_id = vorgang.projekt_id or (auftrag.projekt_id if auftrag else None)
    projekt = await session.get(Projekt, projekt_id) if projekt_id else None
    return auftrag, projekt


async def rechnungsempfaenger_id(session: AsyncSession, vorgang: Vorgang) -> UUID:
    """Auftrag.rechnung_an ?? Projekt.rechnung_an ?? Kunde des Vorgangs. Ein geloeschter abweichender
    Empfaenger wird uebersprungen."""
    auftrag, projekt = await _auftrag_und_projekt(session, vorgang)
    for quelle in (auftrag, projekt):
        if quelle is not None and quelle.rechnung_an_kunde_id is not None:
            kunde = await session.get(Kunde, quelle.rechnung_an_kunde_id)
            if kunde is not None and kunde.geloescht_am is None:
                return kunde.id
    return vorgang.kunde_id


async def kunden_referenz_und_leistungsort(
    session: AsyncSession, vorgang: Vorgang, empfaenger: Kunde
) -> tuple[str | None, dict | None]:
    """(kunden_referenz, leistungsort) fuer einen Beleg aus dem Vorgang. Der Leistungsort entsteht nur, wenn
    eine Einheit gesetzt ist oder die Adresse von der des Empfaengers abweicht -- ein Privatkunde zu Hause
    bekommt keine doppelte Adresszeile."""
    auftrag, _ = await _auftrag_und_projekt(session, vorgang)
    referenz = (auftrag.kunden_referenz if auftrag else None) or None

    standort_id = vorgang.standort_id or (auftrag.standort_id if auftrag else None)
    standort = await session.get(Standort, standort_id) if standort_id else None
    if standort is not None and standort.geloescht_am is not None:
        standort = None
    adresse = standort.adresse if standort is not None else vorgang.adresse
    einheit = (vorgang.einheit or (auftrag.einheit if auftrag else None) or "").strip() or None

    adresse = adresse or {}
    hat_adresse = any(adresse.get(k) for k in ("strasse", "plz", "ort"))
    abweichend = hat_adresse and not _adresse_gleich(adresse, empfaenger.adresse)
    if not einheit and not abweichend:
        return referenz, None
    leistungsort = leistungsort_bereinigen(
        {
            "bezeichnung": einheit or (standort.bezeichnung if standort is not None else None),
            "strasse": adresse.get("strasse"),
            "plz": adresse.get("plz"),
            "ort": adresse.get("ort"),
            "land": adresse.get("land"),
        }
    )
    return referenz, leistungsort


def leistungsort_zeile(leistungsort: dict | None) -> str | None:
    """"<strasse>, <plz> <ort> – <bezeichnung>" fuer PDF und Anzeige."""
    if not leistungsort:
        return None
    ort = " ".join(str(leistungsort[k]) for k in ("plz", "ort") if leistungsort.get(k))
    adresse = ", ".join(t for t in (leistungsort.get("strasse"), ort) if t)
    bezeichnung = leistungsort.get("bezeichnung")
    if adresse and bezeichnung:
        return f"{adresse} – {bezeichnung}"
    return adresse or bezeichnung or None


async def rechnung_an_pruefen(
    session: AsyncSession, rechnung_an_kunde_id: UUID | None, kunde_id: UUID | None
) -> UUID | None:
    """Abweichender Rechnungsempfaenger von Auftrag/Projekt: muss im Mandanten existieren (RLS) und darf nicht
    geloescht sein. Entspricht er dem Auftraggeber, wird nichts gespeichert (None = Auftraggeber)."""
    if rechnung_an_kunde_id is None:
        return None
    kunde = await session.get(Kunde, rechnung_an_kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rechnungsempfänger nicht gefunden"
        )
    return None if rechnung_an_kunde_id == kunde_id else rechnung_an_kunde_id


async def kunden_kurz(session: AsyncSession, ids: set[UUID]) -> dict[UUID, KundeKurz]:
    if not ids:
        return {}
    zeilen = await session.execute(select(Kunde.id, Kunde.name).where(Kunde.id.in_(ids)))
    return {z[0]: KundeKurz(id=z[0], name=z[1]) for z in zeilen}
