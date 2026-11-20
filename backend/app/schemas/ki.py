from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class KiAnfrageRead(BaseModel):
    client_name: str
    scopes_angefragt: list[str]
    schreiben_erlaubt: bool
    redirect_host: str


class KiAutorisieren(BaseModel):
    anfrage: str = Field(min_length=1)
    scopes: list[str]


class KiAblehnen(BaseModel):
    anfrage: str = Field(min_length=1)


class KiRedirect(BaseModel):
    redirect_url: str


class KiVerbindungRead(BaseModel):
    id: UUID
    client_name: str
    scopes: list[str]
    user_id: UUID
    user_name: str
    erstellt_am: datetime
    zuletzt_genutzt_am: datetime | None


KiAktionStatus = Literal["ausgefuehrt", "vorgeschlagen", "abgelehnt", "verfallen", "fehlgeschlagen", "rueckgaengig"]


class KiRefRead(BaseModel):
    typ: str
    id: str
    label: str


class KiAenderungRead(BaseModel):
    """Nur Anzeigewerte; die rohen Werte (fuer das Rueckgaengig) verlassen den Server nicht."""

    typ: str
    id: str
    label: str
    feld: str
    feld_label: str
    vorher: str | None
    nachher: str | None


class KiAktionRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    ki_verbindung_id: UUID | None
    client_name: str | None
    tool: str
    aktionsart: str
    stufe: int
    status: KiAktionStatus
    zusammenfassung: str
    ziele: list[KiRefRead]
    erzeugt: list[KiRefRead]
    aenderungen: list[KiAenderungRead]
    rueckgaengig_moeglich: bool
    rueckgaengig_bis: datetime | None
    rueckgaengig_am: datetime | None
    rueckgaengig_von_name: str | None
    fehler: str | None
    erstellt_am: datetime


class KiAktionenListe(BaseModel):
    eintraege: list[KiAktionRead]
    gesamt: int


class KiKonflikt(BaseModel):
    label: str
    feld_label: str
    erwartet_anzeige: str | None
    aktuell_anzeige: str | None
