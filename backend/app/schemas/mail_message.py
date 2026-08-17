from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MailFolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    imap_name: str
    anzeigename: str
    sortierung: int
    letzter_sync_am: datetime | None


class MailAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dateiname: str
    mimetype: str
    groesse_bytes: int
    eingebettet: bool


class MailMessageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folder_id: UUID
    von_name: str | None
    von_adresse: str | None
    betreff: str
    ausschnitt: str
    datum: datetime | None
    gelesen: bool
    hat_anhang: bool


class MailMessageListResponse(BaseModel):
    items: list[MailMessageListItem]
    next_cursor: str | None


class MailMessageDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folder_id: UUID
    von_name: str | None
    von_adresse: str | None
    an: list[str]
    cc: list[str]
    betreff: str
    body_text: str | None
    body_html: str | None
    datum: datetime | None
    gelesen: bool
    message_id_header: str | None
    anhaenge: list[MailAttachmentRead]


class MailMessageUpdate(BaseModel):
    gelesen: bool


class MailNachrichtSenden(BaseModel):
    an: list[EmailStr] = Field(min_length=1)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)
    betreff: str
    text: str


class MailNachrichtAntworten(BaseModel):
    # An/Cc werden vom Client explizit mitgeschickt (nicht serverseitig aus
    # der Original-Nachricht abgeleitet) -- so kann dieselbe Route sowohl
    # fuer "Antworten" (nur Absender) als auch "Allen antworten" (Absender +
    # alle Empfaenger ausser sich selbst) verwendet werden, ohne dass der
    # Server raten muss, welche der beiden Absichten gemeint ist.
    an: list[EmailStr] = Field(min_length=1)
    cc: list[EmailStr] = Field(default_factory=list)
    text: str


class MailNachrichtWeiterleiten(BaseModel):
    an: list[EmailStr] = Field(min_length=1)
    text: str = ""
