"""Streaming-ZIP fuer Mandanten-Exporte: schreibt in eine Datei auf der Platte (nie komplett
im Arbeitsspeicher), haelt je Datei Groesse und SHA-256 fuer das Manifest."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import IO, Any
from uuid import UUID

from botocore.exceptions import ClientError
from starlette.concurrency import run_in_threadpool

from app.services import storage_service
from app.services.csv_service import formel_sicher

_CHUNK = 1024 * 1024


def json_wert(wert: Any) -> Any:
    """JSON-tauglicher Wert ohne Genauigkeitsverlust (Decimal als Text, ISO-Datum)."""
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, (datetime, date)):
        return wert.isoformat()
    if isinstance(wert, UUID):
        return str(wert)
    if isinstance(wert, dict):
        return {str(k): json_wert(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [json_wert(v) for v in wert]
    return wert


def csv_zelle(wert: Any) -> Any:
    if wert is None:
        return ""
    wert = json_wert(wert)
    if isinstance(wert, (dict, list)):
        wert = json.dumps(wert, ensure_ascii=False, sort_keys=True)
    if isinstance(wert, bool):
        return "true" if wert else "false"
    return formel_sicher(wert) if isinstance(wert, str) else wert


@dataclass
class DateiInfo:
    pfad: str
    groesse: int
    sha256: str


class _HashSchreiber(io.RawIOBase):
    """Schreibt in einen ZIP-Eintrag und rechnet dabei Hash und Groesse mit."""

    def __init__(self, ziel: IO[bytes]) -> None:
        self._ziel = ziel
        self.hash = hashlib.sha256()
        self.groesse = 0

    def writable(self) -> bool:
        return True

    def write(self, daten) -> int:  # type: ignore[override]
        daten = bytes(daten)
        self._ziel.write(daten)
        self.hash.update(daten)
        self.groesse += len(daten)
        return len(daten)

    def close(self) -> None:
        if not self.closed:
            self._ziel.close()
        super().close()


class ZipSchreiber:
    def __init__(self, ziel: IO[bytes]) -> None:
        self._zip = zipfile.ZipFile(ziel, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)
        self.dateien: list[DateiInfo] = []
        self.uebersprungen: list[dict[str, str]] = []
        self._offen: _HashSchreiber | None = None

    def _eintrag(self, pfad: str):
        info = zipfile.ZipInfo(pfad)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.date_time = (2000, 1, 1, 0, 0, 0)  # reproduzierbar, die Zeit steht im Manifest
        raw = self._zip.open(info, "w", force_zip64=True)
        self._offen = _HashSchreiber(raw)
        return self._offen

    def _abschliessen(self, pfad: str, schreiber: _HashSchreiber) -> None:
        schreiber.close()
        self._offen = None
        self.dateien.append(DateiInfo(pfad, schreiber.groesse, schreiber.hash.hexdigest()))

    def bytes_hinzufuegen(self, pfad: str, daten: bytes) -> None:
        s = self._eintrag(pfad)
        s.write(daten)
        self._abschliessen(pfad, s)

    def tabelle_beginnen(self, basis: str, spalten: list[str]) -> "TabellenSchreiber":
        return TabellenSchreiber(self, basis, spalten)

    def tabelle_hinzufuegen(self, basis: str, spalten: list[str], zeilen: Iterable[dict[str, Any]]) -> int:
        tabelle = self.tabelle_beginnen(basis, spalten)
        for zeile in zeilen:
            tabelle.zeile(zeile)
        return tabelle.abschliessen()

    async def s3_objekt_hinzufuegen(self, pfad: str, key: str) -> bool:
        """Streamt ein Objekt aus dem Objektspeicher in den ZIP. False (und Vermerk im Manifest),
        wenn es dort fehlt -- ein fehlendes Einzelobjekt bricht den Export nicht ab."""

        def _vorhanden() -> bool:
            try:
                storage_service._internal_client.head_object(Bucket=storage_service.BUCKET, Key=key)
            except ClientError:
                return False
            return True

        if not await run_in_threadpool(_vorhanden):
            self.uebersprungen.append({"pfad": pfad, "grund": "Objekt im Speicher nicht gefunden"})
            return False

        schreiber = self._eintrag(pfad)

        def _kopieren() -> None:
            obj = storage_service._internal_client.get_object(Bucket=storage_service.BUCKET, Key=key)
            for chunk in obj["Body"].iter_chunks(chunk_size=_CHUNK):
                schreiber.write(chunk)

        await run_in_threadpool(_kopieren)
        self._abschliessen(pfad, schreiber)
        return True

    def manifest_schreiben(self, kopf: dict[str, Any]) -> bytes:
        manifest = {
            **kopf,
            "dateien": [{"pfad": d.pfad, "groesse_bytes": d.groesse, "sha256": d.sha256} for d in self.dateien],
            "uebersprungen": self.uebersprungen,
        }
        daten = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        s = self._eintrag("manifest.json")
        s.write(daten)
        s.close()
        return daten

    def schliessen(self) -> None:
        self._zip.close()

    def abbrechen(self) -> None:
        """Nach einem Fehler: offenen Eintrag und ZIP sauber schliessen (sonst meldet ZipFile.__del__
        beim Aufraeumen unlesbare Folgefehler). Das Ergebnis wird verworfen."""
        try:
            if self._offen is not None:
                self._offen.close()
                self._offen = None
            self._zip.close()
        except Exception:  # noqa: BLE001
            pass


class TabellenSchreiber:
    """Schreibt <basis>.csv (UTF-8 mit BOM, Semikolon) und <basis>.json (Array) aus einem
    einzigen Durchlauf. Ein ZIP erlaubt nur einen offenen Eintrag: die CSV geht direkt
    hinein, das JSON zunaechst in eine Zwischendatei (bei grossen Tabellen auf der Platte).
    Waehrend einer offenen Tabelle darf kein anderer Eintrag geschrieben werden."""

    def __init__(self, zip_: ZipSchreiber, basis: str, spalten: list[str]) -> None:
        self._zip = zip_
        self._basis = basis
        self._spalten = spalten
        self._json = tempfile.SpooledTemporaryFile(max_size=8 * _CHUNK)
        self._csv_s = zip_._eintrag(f"{basis}.csv")
        self._csv_text = io.TextIOWrapper(self._csv_s, encoding="utf-8-sig", newline="", write_through=True)
        self._writer = csv.writer(self._csv_text, delimiter=";", lineterminator="\r\n")
        self._writer.writerow([formel_sicher(sp) for sp in spalten])
        self._json.write(b"[")
        self.anzahl = 0

    def zeile(self, zeile: dict[str, Any]) -> None:
        self._writer.writerow([csv_zelle(zeile.get(sp)) for sp in self._spalten])
        eintrag = json.dumps({sp: json_wert(zeile.get(sp)) for sp in self._spalten}, ensure_ascii=False)
        self._json.write(((",\n" if self.anzahl else "\n") + eintrag).encode("utf-8"))
        self.anzahl += 1

    def abschliessen(self) -> int:
        self._json.write(b"\n]\n")
        self._csv_text.flush()
        self._csv_text.detach()
        self._zip._abschliessen(f"{self._basis}.csv", self._csv_s)
        self._json.seek(0)
        json_s = self._zip._eintrag(f"{self._basis}.json")
        while chunk := self._json.read(_CHUNK):
            json_s.write(chunk)
        self._zip._abschliessen(f"{self._basis}.json", json_s)
        self._json.close()
        return self.anzahl
