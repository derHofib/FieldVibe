import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MailFolder(TimestampMixin, Base):
    """Ein IMAP-Ordner (INBOX, Gesendet, Papierkorb, benutzerdefiniert...)
    eines Postfachs. last_uid ist der Sync-Fortschritt je Ordner (ein
    Ordner hat einen eigenen UID-Zaehler, deshalb hier statt am Account) --
    gleiches Prinzip wie MandantIntegration.config["last_uid"] beim
    Rechnungseingang-Import, nur pro Ordner statt global.

    uidvalidity: aendert sich der Wert serverseitig (z.B. nach Mailbox-
    Neuaufbau), sind alle bisherigen UIDs ungueltig -- der Sync erkennt das
    und baut den Ordner komplett neu auf (siehe mail_sync_service), statt
    wie beim Rechnungseingang-Import diesen Fall bewusst zu ignorieren: bei
    einem taeglich genutzten persoenlichen Postfach faellt ein "Nachrichten
    verschwinden/verdoppeln sich" deutlich staerker auf als beim
    Rechnungseingang."""

    __tablename__ = "mail_folders"
    __table_args__ = (
        UniqueConstraint("mail_account_id", "imap_name", name="uq_mail_folders_account_imap_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False
    )

    imap_name: Mapped[str] = mapped_column(Text, nullable=False)
    anzeigename: Mapped[str] = mapped_column(Text, nullable=False)

    uidvalidity: Mapped[int | None] = mapped_column(BigInteger)
    last_uid: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    letzter_sync_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reihenfolge in der Ordnerliste (INBOX zuerst, Rest alphabetisch) --
    # siehe mail_sync_service._sortierschluessel.
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
