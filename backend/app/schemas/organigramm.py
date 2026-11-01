from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.rechte_registry import scopes_fuer_bereich
from app.schemas.account_typ import RechteAktion, RechteBereich

PositionTyp = Literal["linie", "stabsstelle"]
PositionStatus = Literal["besetzt", "vakant", "geplant"]
BesetzungArt = Literal["regulaer", "vertretung"]
OrgEinheitTyp = Literal["bereich", "abteilung", "team"]
Wirkung = Literal["erlauben", "verweigern"]
Scope = Literal["eigene", "team", "teilbaum", "bereich", "mandant"]


class OrgEinheitRef(BaseModel):
    id: UUID
    name: str
    typ: str


class AccountTypRef(BaseModel):
    id: UUID
    name: str


class BesetzungRead(BaseModel):
    """user_id/name fehlen (bzw. name=None), wenn der Abrufer den Nutzer nicht
    sehen darf (DSGVO) -- die Antwort wird mit response_model_exclude_unset ausgeliefert."""

    id: UUID
    user_id: UUID | None = None
    name: str | None = None
    art: str
    gueltig_von: datetime
    gueltig_bis: datetime | None


class PositionRead(BaseModel):
    """kontext=True: Knoten nur als Pfad zur Wurzel sichtbar, ohne Details."""

    id: UUID
    parent_id: UUID | None
    titel: str
    typ: str
    kontext: bool = False
    ist_ausser_linie: bool | None = None
    status: PositionStatus | None = None
    ebene: int | None = None
    org_einheit: OrgEinheitRef | None = None
    account_typ: AccountTypRef | None = None
    geplant: bool | None = None
    soll_besetzung: int | None = None
    ist_besetzung: int | None = None
    gueltig_ab: date | None = None
    gueltig_bis: date | None = None
    archiviert_am: datetime | None = None
    reihenfolge: int | None = None
    besetzungen: list[BesetzungRead] = Field(default_factory=list)


class PositionCreate(BaseModel):
    parent_id: UUID
    typ: PositionTyp = "linie"
    titel: str = Field(min_length=1)
    ebene: int | None = None
    org_einheit_id: UUID | None = None
    account_typ_id: UUID | None = None
    geplant: bool = False
    soll_besetzung: int = Field(default=1, ge=0)
    gueltig_ab: date | None = None
    gueltig_bis: date | None = None
    reihenfolge: int = 0

    @model_validator(mode="after")
    def _zeitraum(self) -> "PositionCreate":
        if self.gueltig_ab and self.gueltig_bis and self.gueltig_bis < self.gueltig_ab:
            raise ValueError("gueltig_bis darf nicht vor gueltig_ab liegen")
        return self


class PositionUpdate(BaseModel):
    parent_id: UUID | None = None
    typ: PositionTyp | None = None
    titel: str | None = Field(default=None, min_length=1)
    ebene: int | None = None
    org_einheit_id: UUID | None = None
    account_typ_id: UUID | None = None
    geplant: bool | None = None
    soll_besetzung: int | None = Field(default=None, ge=0)
    gueltig_ab: date | None = None
    gueltig_bis: date | None = None
    reihenfolge: int | None = None


class RechtOverrideIn(BaseModel):
    bereich: RechteBereich
    aktion: RechteAktion
    wirkung: Wirkung
    # Beim Erlauben optional (dann Basis-Scope bzw. mandant, siehe Engine); beim
    # Verweigern ohne Bedeutung und wird nicht gespeichert.
    scope: Scope | None = None

    @model_validator(mode="after")
    def _gegen_registry(self) -> "RechtOverrideIn":
        from app.core.rechte_registry import ist_gueltig

        if not ist_gueltig(self.bereich, self.aktion):
            raise ValueError("Diese Aktion gibt es für diesen Bereich nicht")
        if self.scope is not None and self.scope not in scopes_fuer_bereich(self.bereich):
            raise ValueError(f"Der Bereich „{self.bereich}“ unterstützt den Scope „{self.scope}“ nicht")
        if self.wirkung == "verweigern":
            self.scope = None
        return self


class RechtOverrideRead(BaseModel):
    bereich: str
    aktion: str
    wirkung: str
    scope: str | None


class EffektivesRechtRead(BaseModel):
    bereich: str
    aktion: str
    scope: str
    herkunft: list[dict]


class RechtDiffRead(BaseModel):
    """Abweichung der Position von der Typ-Vorlage."""

    bereich: str
    aktion: str
    art: Literal["hinzugefuegt", "entfernt", "scope_geaendert"]
    typ_scope: str | None
    position_scope: str | None


class PositionDetailRead(PositionRead):
    alle_besetzungen: list[BesetzungRead] = Field(default_factory=list)
    overrides: list[RechtOverrideRead] = Field(default_factory=list)
    effektive_rechte: list[EffektivesRechtRead] = Field(default_factory=list)
    diff_zur_vorlage: list[RechtDiffRead] = Field(default_factory=list)
    unterpositionen: int = 0


class BesetzungCreate(BaseModel):
    user_id: UUID
    art: BesetzungArt = "regulaer"
    gueltig_von: datetime | None = None
    gueltig_bis: datetime | None = None


class BesetzungUpdate(BaseModel):
    # None/fehlend = jetzt beenden (Freistellung).
    gueltig_bis: datetime | None = None


class BesetzungErgebnis(BaseModel):
    besetzung: BesetzungRead
    warnung: str | None = None


class EffektivRead(BaseModel):
    user_id: UUID | None = None
    position_id: UUID | None = None
    rolle: str | None = None
    alle_rechte: bool = False
    rechte: list[EffektivesRechtRead]
    verweigert: list[dict] = Field(default_factory=list)


class OrgEinheitRead(BaseModel):
    id: UUID
    name: str
    typ: str
    parent_id: UUID | None
    archiviert_am: datetime | None


class OrgEinheitCreate(BaseModel):
    name: str = Field(min_length=1)
    typ: OrgEinheitTyp
    parent_id: UUID | None = None


class OrgEinheitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    typ: OrgEinheitTyp | None = None
    parent_id: UUID | None = None
