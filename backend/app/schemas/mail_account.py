from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

MailVerschluesselung = Literal["ssl", "starttls", "keine"]


class MailAccountCreate(BaseModel):
    name: str
    email_adresse: EmailStr

    imap_host: str
    imap_port: int = 993
    imap_verschluesselung: MailVerschluesselung = "ssl"
    imap_benutzername: str

    smtp_host: str
    smtp_port: int = 587
    smtp_verschluesselung: MailVerschluesselung = "starttls"
    smtp_benutzername: str

    # Ein Passwort fuer beide Protokolle -- siehe Kommentar am Model.
    passwort: str

    signatur: str | None = None
    aktiv: bool = True


class MailAccountUpdate(BaseModel):
    name: str | None = None
    email_adresse: EmailStr | None = None

    imap_host: str | None = None
    imap_port: int | None = None
    imap_verschluesselung: MailVerschluesselung | None = None
    imap_benutzername: str | None = None

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_verschluesselung: MailVerschluesselung | None = None
    smtp_benutzername: str | None = None

    # Optional: nur wenn mitgeschickt, wird das gespeicherte Passwort
    # ersetzt (siehe app/api/routes/mail_accounts.py) -- sonst muesste der
    # Nutzer bei jeder Aenderung (z.B. nur die Signatur) sein Passwort
    # erneut eingeben.
    passwort: str | None = None

    signatur: str | None = None
    aktiv: bool | None = None


class MailAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email_adresse: str

    imap_host: str
    imap_port: int
    imap_verschluesselung: MailVerschluesselung
    imap_benutzername: str

    smtp_host: str
    smtp_port: int
    smtp_verschluesselung: MailVerschluesselung
    smtp_benutzername: str

    signatur: str | None
    aktiv: bool
    letzter_sync_am: datetime | None
    letzter_sync_fehler: str | None

    created_at: datetime
    updated_at: datetime

    # Bewusst kein Passwort-Feld -- das verschluesselte Passwort verlaesst
    # den Server nie wieder in Klartext-Richtung Client.


class MailAccountVerbindungTest(BaseModel):
    """Fuer den 'Verbindung testen'-Button vor dem eigentlichen Speichern:
    dieselben Felder wie Create, damit ein Nutzer sein Postfach pruefen
    kann, bevor er es anlegt."""

    imap_host: str
    imap_port: int = 993
    imap_verschluesselung: MailVerschluesselung = "ssl"
    imap_benutzername: str

    smtp_host: str
    smtp_port: int = 587
    smtp_verschluesselung: MailVerschluesselung = "starttls"
    smtp_benutzername: str

    passwort: str
