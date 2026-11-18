"""Uebersetzt die einfache Abschnitts-Struktur, die Claude liefert, in Gruppen und Felder des
Formular-Baukastens (reine Logik ohne I/O, damit sie ohne Datenbank testbar ist)."""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.form_modul import FormFeldTyp

MAX_ABSCHNITTE = 30
MAX_FELDER_JE_ABSCHNITT = 60
MAX_OPTIONEN = 50

# Nur diese Typen haben eine Auswahlliste (optionen.werte, so liest sie der Baukasten und die Feld-App).
TYPEN_MIT_OPTIONEN = ("dropdown", "mehrfachauswahl")

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"})


class FeldEntwurf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[str, Field(min_length=1, max_length=200, description="Beschriftung des Feldes.")]
    typ: Annotated[
        FormFeldTyp,
        Field(
            description=(
                "Feldtyp: text, textarea, zahl, datum, dropdown, mehrfachauswahl, ja_nein, bewertung (1-5), foto, "
                "unterschrift, gps, qr_scan, datei, email, telefon, betrag, adresse, foto_plan."
            )
        ),
    ]
    pflicht: Annotated[bool, Field(description="Pflichtfeld: ohne Wert kein Abschluss in der App.")] = False
    hilfetext: Annotated[str | None, Field(max_length=500, description="Kurzer Hinweis unter dem Feld, z. B. Grenzwert.")] = None
    optionen: Annotated[
        list[str] | None,
        Field(description="Auswahlmöglichkeiten; nur und zwingend bei dropdown und mehrfachauswahl."),
    ] = None


class AbschnittEntwurf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titel: Annotated[str, Field(min_length=1, max_length=200, description="Überschrift des Abschnitts.")]
    wiederholbar: Annotated[
        bool,
        Field(description="true = Abschnitt kann mehrfach ausgefüllt werden (z. B. Mängelliste). Standard false."),
    ] = False
    felder: Annotated[list[FeldEntwurf], Field(min_length=1, max_length=MAX_FELDER_JE_ABSCHNITT)]


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def key_aus(text: str, belegt: set[str], vorsatz: str) -> str:
    """ASCII-Key (^[a-z][a-z0-9_]*$) aus einem Label; eindeutig gegenueber `belegt` (Gruppen- und
    Feld-Keys teilen sich im Baukasten einen Namensraum). Traegt den Key in `belegt` ein."""
    s = unicodedata.normalize("NFKD", text.translate(_UMLAUTE)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = f"{vorsatz}_{s}".strip("_")
    s = s[:50].rstrip("_")
    kandidat, n = s, 2
    while kandidat in belegt:
        kandidat = f"{s}_{n}"
        n += 1
    belegt.add(kandidat)
    return kandidat


def pruefe_feld(feld: FeldEntwurf, wo: str) -> list[str]:
    """Bereinigte Optionen (nur fuer dropdown/mehrfachauswahl) oder ToolError."""
    optionen = [o.strip() for o in (feld.optionen or []) if o and o.strip()]
    if feld.typ in TYPEN_MIT_OPTIONEN:
        if not optionen:
            raise ToolError(f"{wo}: Feld „{feld.label}“ ({feld.typ}) braucht mindestens eine Option in „optionen“.")
        if len(optionen) > MAX_OPTIONEN:
            raise ToolError(f"{wo}: Feld „{feld.label}“ hat mehr als {MAX_OPTIONEN} Optionen.")
        if len({norm(o) for o in optionen}) != len(optionen):
            raise ToolError(f"{wo}: Feld „{feld.label}“ hat doppelte Optionen.")
    elif feld.optionen:
        raise ToolError(f"{wo}: „optionen“ gibt es nur bei dropdown und mehrfachauswahl, nicht bei „{feld.typ}“.")
    return optionen


def pruefe_abschnitte(abschnitte: list[AbschnittEntwurf]) -> None:
    if not abschnitte:
        raise ToolError("Mindestens ein Abschnitt ist nötig.")
    if len(abschnitte) > MAX_ABSCHNITTE:
        raise ToolError(f"Höchstens {MAX_ABSCHNITTE} Abschnitte je Vorlage.")
    titel = [norm(a.titel) for a in abschnitte]
    if len(set(titel)) != len(titel):
        raise ToolError("Abschnittstitel müssen eindeutig sein.")
    for a in abschnitte:
        labels = [norm(f.label) for f in a.felder]
        if len(set(labels)) != len(labels):
            raise ToolError(f"Abschnitt „{a.titel}“: Feld-Beschriftungen müssen innerhalb eines Abschnitts eindeutig sein.")
        for f in a.felder:
            pruefe_feld(f, f"Abschnitt „{a.titel}“")


@dataclass
class Schritt:
    """Ein REST-Aufruf beim Anlegen bzw. Aendern einer Vorlage."""

    art: str  # "groups" | "fields" (POST) | "fields_patch" (PATCH auf feld_id)
    body: dict[str, Any]
    beschreibung: str
    feld_id: str | None = None


@dataclass
class Plan:
    schritte: list[Schritt] = field(default_factory=list)


def feld_body(feld: FeldEntwurf, key: str, gruppe_key: str, reihenfolge: int, wo: str) -> dict[str, Any]:
    optionen = pruefe_feld(feld, wo)
    return {
        "key": key,
        "feld_typ": feld.typ,
        "label": {"de": feld.label},
        "hilfetext": feld.hilfetext,
        "pflichtfeld": feld.pflicht,
        "optionen": {"werte": optionen} if optionen else {},
        "group_key": gruppe_key,
        "reihenfolge": reihenfolge,
    }


def abschnitte_planen(abschnitte: list[AbschnittEntwurf], belegt: set[str], start: int = 0) -> Plan:
    """Gruppe zuerst, dann ihre Felder. repeatable wird immer explizit gesetzt: der Standard der
    API waere true, ein nicht wiederholbarer Abschnitt wuerde sonst als Mehrfach-Liste erscheinen."""
    plan = Plan()
    for i, abschnitt in enumerate(abschnitte):
        gruppe_key = key_aus(abschnitt.titel, belegt, "abschnitt")
        plan.schritte.append(
            Schritt(
                "groups",
                {
                    "key": gruppe_key,
                    "label": {"de": abschnitt.titel},
                    "repeatable": abschnitt.wiederholbar,
                    "reihenfolge": start + i,
                },
                f"Abschnitt „{abschnitt.titel}“",
            )
        )
        for j, f in enumerate(abschnitt.felder):
            plan.schritte.append(
                Schritt(
                    "fields",
                    feld_body(f, key_aus(f.label, belegt, "feld"), gruppe_key, j, f"Abschnitt „{abschnitt.titel}“"),
                    f"Feld „{f.label}“ in „{abschnitt.titel}“",
                )
            )
    return plan


def zusammenfassung(abschnitte: list[AbschnittEntwurf]) -> list[dict[str, Any]]:
    return [
        {
            "abschnitt": a.titel,
            "wiederholbar": a.wiederholbar,
            "felder": [f"{f.label} ({f.typ}{', Pflicht' if f.pflicht else ''})" for f in a.felder],
        }
        for a in abschnitte
    ]
