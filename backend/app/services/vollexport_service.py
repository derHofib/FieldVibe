"""Mandanten-Vollexport (Art. 20 DSGVO, Datenportabilitaet / Anbieterwechsel).

Liest ausschliesslich ueber eine Mandanten-Session (RLS) und zusaetzlich mit explizitem
Mandantenfilter. Streamt Tabellen (CSV + JSON) und Objekte (Belege, Fotos, Dokumente) in
ein ZIP auf der Platte; nichts wird komplett im Arbeitsspeicher gehalten. Nicht
enthalten und im README genannt: Passwort-Hashes, MFA-Geheimnisse, Tokens, Integrationen
und Zugangsdaten (Mail-Konten, Schnittstellen), Postfach-Inhalte, interne Zaehler."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot, AngebotPosition
from app.models.angebot_annahme import AngebotAnnahme
from app.models.anlage import Anlage
from app.models.audit_log import AuditLog
from app.models.bestellung import Bestellung, BestellungPosition
from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungPosition, EingangsrechnungZahlung
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.material import Material, MaterialBestand, MaterialBewegung, MaterialVerwendung
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.rechnung import Rechnung, RechnungPosition, RechnungZahlung
from app.models.standort import Standort
from app.models.termin import Termin
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.services import audit_service, storage_service
from app.services.export_zip import ZipSchreiber, json_wert

_SEITE = 500
EXPORT_VERSION = 1


@dataclass(frozen=True)
class Tabelle:
    name: str
    modell: type
    beschreibung: str
    nur: tuple[str, ...] | None = None  # Whitelist (sensible Tabellen)
    ohne: frozenset[str] = frozenset()  # Sperrliste (alle anderen Spalten werden exportiert)


# Reihenfolge = Reihenfolge im README.
TABELLEN: tuple[Tabelle, ...] = (
    Tabelle("kunden", Kunde, "Kunden (inkl. Papierkorb, Spalte geloescht_am)"),
    Tabelle("standorte", Standort, "Standorte der Kunden"),
    Tabelle("anlagen", Anlage, "Anlagen/Betriebsmittel (inkl. Lagerorte und Fahrzeuge)"),
    Tabelle("vertraege", Vertrag, "Wartungs-/Serviceverträge"),
    Tabelle("vorgaenge", Vorgang, "Vorgänge (Aufträge/Tickets)"),
    Tabelle("vorgang_verlauf", VorgangEvent, "Verlauf der Vorgänge (Chat, Statusänderungen, Foto-/Dokumentverweise)"),
    Tabelle("termine", Termin, "Termine"),
    Tabelle("maengel", Mangel, "Mängel"),
    Tabelle("pruefzyklen", Pruefzyklus, "Prüfzyklen"),
    Tabelle("pruefmittel", Pruefmittel, "Prüfmittel/Messgeräte"),
    Tabelle("angebote", Angebot, "Angebote"),
    Tabelle("angebot_positionen", AngebotPosition, "Angebotspositionen"),
    Tabelle("angebot_annahmen", AngebotAnnahme, "Nachweise zu Annahme/Ablehnung/Widerruf im Kundenportal"),
    Tabelle("rechnungen", Rechnung, "Ausgangsrechnungen, Gutschriften, Stornobelege"),
    Tabelle("rechnung_positionen", RechnungPosition, "Rechnungspositionen"),
    Tabelle("rechnung_zahlungen", RechnungZahlung, "Zahlungseingänge zu Rechnungen"),
    Tabelle("eingangsrechnungen", Eingangsrechnung, "Eingangsrechnungen"),
    Tabelle("eingangsrechnung_positionen", EingangsrechnungPosition, "Positionen der Eingangsrechnungen"),
    Tabelle("eingangsrechnung_zahlungen", EingangsrechnungZahlung, "Zahlungen zu Eingangsrechnungen"),
    Tabelle("lieferanten", Lieferant, "Lieferanten"),
    Tabelle("bestellungen", Bestellung, "Bestellungen"),
    Tabelle("bestellung_positionen", BestellungPosition, "Bestellpositionen"),
    Tabelle("material", Material, "Material-Stammdaten"),
    Tabelle("material_bestand", MaterialBestand, "Materialbestände je Lagerort"),
    Tabelle("material_bewegungen", MaterialBewegung, "Materialbewegungen"),
    Tabelle("material_verwendungen", MaterialVerwendung, "Materialverbrauch an Vorgängen"),
    Tabelle("zeiterfassung", Zeiterfassung, "Zeiten (Arbeits-, Fahr-, Vorgangszeiten)"),
    Tabelle(
        "nutzer",
        User,
        "Mitarbeiter-Konten (ohne Passwort-Hash, MFA-Geheimnis, Wiederherstellungscodes, Token-Zähler)",
        nur=("id", "mandant_id", "email", "name", "role", "account_typ_id", "aktiv", "mfa_aktiv", "created_at", "updated_at"),
    ),
    Tabelle("protokoll", AuditLog, "Mandanten-Protokoll (append-only, siehe auch Kettenkopf im Manifest)"),
)

# Mandanten-Einstellungen: Whitelist, firmendaten zusaetzlich von Geheimnis-Schluesseln bereinigt.
EINSTELLUNGEN_FELDER = (
    "id", "name", "slug", "branche", "status", "branding", "deaktivierte_module", "firmendaten",
    "scheduler_stunde_utc", "wiedervorlage_standard_tage", "standard_lohn_gemeinkosten_prozent",
    "standard_gewinn_wagnis_prozent", "km_satz_netto", "fahrzeit_satz_netto", "fahrzeit_abrechnung",
    "bundesland", "created_at", "updated_at",
)


def spalten_von(t: Tabelle) -> list[str]:
    alle = [c.key for c in sa_inspect(t.modell).mapper.column_attrs]
    if t.nur is not None:
        return [c for c in alle if c in t.nur]
    return [c for c in alle if c not in t.ohne]


def _sicherer_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "datei"


def _endung(key: str, standard: str = "bin") -> str:
    return key.rsplit(".", 1)[-1].lower() if "." in key.rsplit("/", 1)[-1] else standard


async def _tabelle_schreiben(
    session: AsyncSession, zip_: ZipSchreiber, t: Tabelle, mandant_id: UUID
) -> tuple[int, list[dict[str, Any]]]:
    """Schreibt eine Tabelle; liefert Zeilenzahl und die Datensaetze (id + Objektschluessel) fuer
    den Objekt-Durchlauf zurueck -- bei Tabellen ohne Objekte eine leere Liste."""
    spalten = spalten_von(t)
    tabelle = zip_.tabelle_beginnen(f"daten/{t.name}", spalten)
    objekte: list[dict[str, Any]] = []
    stmt = (
        select(t.modell)
        .where(t.modell.mandant_id == mandant_id)
        .order_by(t.modell.id)
        .execution_options(yield_per=_SEITE)
    )
    ergebnis = await session.stream(stmt)
    async for zeile in ergebnis.scalars():
        daten = {sp: getattr(zeile, sp) for sp in spalten}
        tabelle.zeile(daten)
        objekte.extend(_objekte_der_zeile(t.name, zeile))
    return tabelle.abschliessen(), objekte


def _objekte_der_zeile(tabelle: str, zeile: Any) -> list[dict[str, Any]]:
    """Objektschluessel, die zu dieser Zeile gehoeren (Pfad im ZIP wird spaeter gebildet)."""
    if tabelle == "rechnungen":
        gefunden = []
        basis = _sicherer_name(zeile.rechnungsnummer)
        if zeile.pdf_object_key:
            gefunden.append({"pfad": f"belege/rechnungen/{basis}.pdf", "key": zeile.pdf_object_key})
        if zeile.xml_object_key:
            name = f"{basis}-xrechnung.xml" if zeile.e_rechnung_profil == "xrechnung" else f"{basis}-factur-x.xml"
            gefunden.append({"pfad": f"belege/rechnungen/{name}", "key": zeile.xml_object_key})
        return gefunden
    if tabelle == "eingangsrechnungen":
        basis = f"{zeile.rechnungsdatum.isoformat()}_{str(zeile.id)[:8]}"
        gefunden = []
        if zeile.beleg_object_key:
            gefunden.append(
                {"pfad": f"belege/eingangsrechnungen/{basis}.{_endung(zeile.beleg_object_key, 'pdf')}", "key": zeile.beleg_object_key}
            )
        if zeile.xml_object_key:
            gefunden.append({"pfad": f"belege/eingangsrechnungen/{basis}.xml", "key": zeile.xml_object_key})
        return gefunden
    if tabelle == "vorgang_verlauf" and zeile.event_type in ("foto", "dokument", "unterschrift"):
        key = (zeile.payload or {}).get("key")
        if key:
            name = _sicherer_name((zeile.payload or {}).get("dateiname") or f"{zeile.event_type}.{_endung(key)}")
            return [
                {"pfad": f"dokumente/vorgaenge/{zeile.vorgang_id}/{str(zeile.id)[:8]}_{name}", "key": key}
            ]
    if tabelle == "kunden" and zeile.logo_object_key:
        return [{"pfad": f"dokumente/kunden/{zeile.id}/logo.{_endung(zeile.logo_object_key, 'png')}", "key": zeile.logo_object_key}]
    return []


README = """\
FieldVibe -- Datenexport
========================

Erzeugt am {zeit} (UTC) fuer den Betrieb "{betrieb}".
Dieser Export enthaelt die Daten Ihres Betriebs in gaengigen, maschinenlesbaren Formaten
(Art. 20 DSGVO). Er kann ohne FieldVibe gelesen werden.

Aufbau
------
  manifest.json      Liste aller Dateien mit Groesse und SHA-256 (Pruefsumme) sowie Hinweise.
  README.txt         Diese Datei.
  einstellungen.json Betriebseinstellungen (ohne Zugangsdaten).
  daten/             Eine Tabelle je Datei, jeweils als .csv und als .json:
                     CSV = UTF-8 mit BOM, Trennzeichen Semikolon, Dezimalpunkt, Datum/Zeit im
                     ISO-Format (UTC). JSON = Array von Objekten, Zahlen mit Nachkommastellen
                     als Text, damit keine Rundung entsteht.
  belege/            Archivierte Rechnungen (PDF, ggf. XML/XRechnung) und Eingangsbelege.
  dokumente/         Fotos, Unterschriften und Dokumente aus Vorgaengen, Kundenlogos.

Datenmodell (Kurzfassung)
-------------------------
Jede Zeile hat eine id (UUID). Verweise heissen <name>_id und zeigen auf die id der
jeweiligen Tabelle (kunde_id -> kunden, vorgang_id -> vorgaenge, rechnung_id -> rechnungen
usw.). Positionen und Zahlungen verweisen auf ihren Beleg. Spalten wie geloescht_am zeigen
Datensaetze aus dem Papierkorb. Dateien in belege/ und dokumente/ gehoeren ueber ihren Pfad
bzw. ueber die Spalten pdf_object_key/xml_object_key/key in den Tabellen zusammen.

Tabellen
--------
{tabellen}

Nicht enthalten
---------------
Passwort-Hashes, MFA-Geheimnisse und Wiederherstellungscodes, Zugriffstokens, Schnittstellen-
und Postfach-Zugangsdaten, Postfach-Inhalte, interne Nummernzaehler. Die Daten anderer
Betriebe sind nie enthalten.

Pruefung
--------
sha256sum -c ist nicht noetig: im manifest.json steht je Datei die SHA-256-Summe. Das Manifest
selbst ist nicht Teil der Summenliste; die Summe des gesamten ZIP zeigt FieldVibe beim Download an.
"""


async def erzeuge(session: AsyncSession, zip_: ZipSchreiber, mandant_id: UUID) -> dict[str, Any]:
    """Schreibt alle Inhalte in den ZIP und liefert die Kopfdaten fuer das Manifest."""
    mandant = await session.get(Mandant, mandant_id)
    jetzt = datetime.now(timezone.utc)
    zeilen_je_tabelle: dict[str, int] = {}
    objekte: list[dict[str, Any]] = []
    for t in TABELLEN:
        anzahl, gefunden = await _tabelle_schreiben(session, zip_, t, mandant_id)
        zeilen_je_tabelle[t.name] = anzahl
        objekte.extend(gefunden)

    einstellungen = {k: json_wert(getattr(mandant, k)) for k in EINSTELLUNGEN_FELDER}
    einstellungen["firmendaten"] = audit_service.bereinigen(einstellungen["firmendaten"])
    zip_.bytes_hinzufuegen("einstellungen.json", json.dumps(einstellungen, ensure_ascii=False, indent=2).encode("utf-8"))
    if mandant.logo_object_key:
        objekte.append(
            {"pfad": f"dokumente/logo-betrieb.{_endung(mandant.logo_object_key, 'png')}", "key": mandant.logo_object_key}
        )

    belegt: set[str] = set()
    for o in objekte:
        pfad, key = o["pfad"], o["key"]
        # Ein Schluessel mit fremdem Mandantenpraefix darf nie in diesen Export (selbst wenn
        # eine Zeile faelschlich darauf zeigt). Altschluessel ohne Praefix stammen aus RLS-Zeilen.
        if storage_service.key_gehoert_zu_mandant(key, mandant_id) is False:
            zip_.uebersprungen.append({"pfad": pfad, "grund": "Objektschluessel gehoert nicht zu diesem Betrieb"})
            continue
        if pfad in belegt:
            continue
        belegt.add(pfad)
        await zip_.s3_objekt_hinzufuegen(pfad, key)

    kette = await audit_service.kette_pruefen(session, mandant_id)
    tabellen_text = "\n".join(
        f"  daten/{t.name:<30} {zeilen_je_tabelle[t.name]:>7} Zeilen  {t.beschreibung}" for t in TABELLEN
    )
    zip_.bytes_hinzufuegen(
        "README.txt",
        README.format(zeit=jetzt.strftime("%d.%m.%Y %H:%M"), betrieb=mandant.name, tabellen=tabellen_text).encode("utf-8"),
    )
    return {
        "export_version": EXPORT_VERSION,
        "art": "vollexport",
        "erstellt_am": jetzt.isoformat(),
        "mandant": {"id": str(mandant_id), "name": mandant.name},
        "zeilen_je_tabelle": zeilen_je_tabelle,
        "protokoll_kettenkopf": {"seq": kette.kopf_seq, "hash": kette.kopf_hash, "kette_ok": kette.ok},
        "hinweis": "Die Summe des manifest.json selbst ist nicht in dateien enthalten.",
    }
