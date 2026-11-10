from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BoardTyp = Literal["frei", "bauplanung", "prozess"]


class BoardCreate(BaseModel):
    name: str
    board_typ: BoardTyp = "frei"
    inhalt_json: dict = Field(default_factory=dict)


class BoardUpdate(BaseModel):
    name: str | None = None
    inhalt_json: dict | None = None


class BoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    board_typ: BoardTyp
    inhalt_json: dict
    hintergrund_object_key: str | None
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime


# Fuer die Board-Uebersicht -- bewusst ohne inhalt_json, das kann bei einem
# vollen Whiteboard beliebig gross werden und wird fuer die Galerie-Karten
# nicht gebraucht (siehe office/boards/OfficeBoardsPage.tsx).
class BoardListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    board_typ: BoardTyp
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime


class BoardHintergrundUrl(BaseModel):
    url: str | None


# Fuer die Datei-Anhang-Karte (office/boards/nodes/DateiAnhangNode.tsx):
# anders als der Grundriss ist der Object-Key hier nicht in einer eigenen
# Board-Spalte gepflegt, sondern lebt im Node-data innerhalb inhalt_json --
# jedes Attachment gehoert zu genau einem Node, ein Board kann beliebig viele
# haben.
class BoardAnhangUpload(BaseModel):
    object_key: str
    url: str
    dateiname: str


class BoardAnhangUrl(BaseModel):
    url: str
