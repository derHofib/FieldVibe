"""Gemeinsame Typen der Import-Verarbeiter (Kunden, Anlagen, Material)."""
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mandant import Mandant
from app.services.datenimport.parser import Tabelle
from app.services.datenimport.werte import bereinige_text

MODI = ("gueltige", "alles_oder_nichts")
CHARGE_MIN, CHARGE_MAX = 10, 1000


class ImportZeitlimit(Exception):
    pass


@dataclass(frozen=True)
class Konfiguration:
    mapping: dict[str, int | None]
    modus: str = "gueltige"
    chargengroesse: int = 200
    dubletten_aktionen: dict[str, str] = field(default_factory=dict)

    def aktion_fuer(self, art: str, standard: str = "ueberspringen") -> str:
        return self.dubletten_aktionen.get(art, standard)

    def als_dict(self) -> dict:
        return {
            "mapping": {k: v for k, v in sorted(self.mapping.items()) if v is not None},
            "modus": self.modus,
            "chargengroesse": self.chargengroesse,
            "dubletten_aktionen": dict(sorted(self.dubletten_aktionen.items())),
        }

    def hash(self) -> str:
        roh = json.dumps(self.als_dict(), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(roh.encode()).hexdigest()


@dataclass
class ZeilenErgebnis:
    nr: int
    status: str = "neu"  # neu | warnung | dublette | fehler
    aktion: str = "anlegen"  # anlegen | aktualisieren | ueberspringen | keine
    meldungen: list[str] = field(default_factory=list)
    vorschau: dict[str, str] = field(default_factory=dict)
    dublette_art: str | None = None
    dublette_von: str | None = None
    # Vorbereitete Schreibdaten des Verarbeiters; nie in der API-Antwort.
    nutzlast: Any = None

    def fehler(self, meldung: str) -> "ZeilenErgebnis":
        self.status, self.aktion = "fehler", "keine"
        self.meldungen.append(meldung)
        return self

    @property
    def wird_geschrieben(self) -> bool:
        return self.status in ("neu", "warnung") or (self.status == "dublette" and self.aktion in ("aktualisieren", "anlegen"))


@dataclass
class Kontext:
    session: AsyncSession
    mandant_id: UUID
    user_id: UUID
    mandant: Mandant
    frist: float
    # Zwischenwerte eines Laufs (z. B. Zentrallager), nie am Verarbeiter selbst: der ist geteilt.
    extra: dict = field(default_factory=dict)

    def frist_pruefen(self) -> None:
        if time.monotonic() > self.frist:
            raise ImportZeitlimit


class Zeilenleser:
    """Zugriff auf die Zellen einer Zeile ueber Feldnamen statt Spaltenindizes."""

    def __init__(self, zellen: list[str], mapping: dict[str, int | None]):
        self._zellen = zellen
        self._mapping = mapping

    def roh(self, feld: str) -> str:
        index = self._mapping.get(feld)
        if index is None or index >= len(self._zellen):
            return ""
        return self._zellen[index]

    def text(self, feld: str, *, einzeilig: bool = True) -> str:
        return bereinige_text(self.roh(feld), einzeilig=einzeilig)

    def zugeordnet(self, feld: str) -> bool:
        return self._mapping.get(feld) is not None


def pydantic_meldung(exc: ValidationError, bezeichnungen: dict[str, str] | None = None) -> str:
    """Deutsche, eingabewertfreie Meldung aus den Pydantic-Fehlern der bestehenden Schemas."""
    bezeichnungen = bezeichnungen or {}
    teile = []
    for fehler in exc.errors():
        feld = str(fehler["loc"][-1]) if fehler.get("loc") else ""
        name = bezeichnungen.get(feld, feld)
        text = str(fehler.get("msg", "")).removeprefix("Value error, ")
        if fehler.get("type") == "value_error":
            teile.append(text)
        elif fehler.get("type") == "missing":
            teile.append(f"{name}: Pflichtfeld fehlt")
        else:
            teile.append(f"{name}: ungültiger Wert")
    return "; ".join(dict.fromkeys(teile)) or "Ungültige Angaben"


def zeilen_iter(tabelle: Tabelle, konfig: Konfiguration):
    for nr, zellen in zip(tabelle.zeilennummern, tabelle.zeilen):
        yield nr, Zeilenleser(zellen, konfig.mapping)


def vorschau_von(werte: dict[str, str], *, max_laenge: int = 80) -> dict[str, str]:
    return {k: (v if len(v) <= max_laenge else v[: max_laenge - 1] + "…") for k, v in werte.items() if v}
