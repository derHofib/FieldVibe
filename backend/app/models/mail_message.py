import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MailMessage(TimestampMixin, Base):
    """Eine einzelne, aus IMAP gespiegelte Nachricht. body_html wird nicht
    weiter saniert/eingebettet -- die Office/Feld-Oberflaeche rendert ihn in
    einem sandboxed iframe (Stufe 4/5), gleiches Risiko wie bei jedem
    Mailclient (externe Bilder/Tracking, aktives HTML), kein
    FieldVibe-spezifisches Problem."""

    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint("folder_id", "uid", name="uq_mail_messages_folder_uid"),
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
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mail_folders.id", ondelete="CASCADE"), nullable=False
    )

    uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id_header: Mapped[str | None] = mapped_column(Text)
    in_reply_to: Mapped[str | None] = mapped_column(Text)
    # Rohe References-Kopfzeile (leerzeichengetrennte Message-IDs) fuer den
    # Thread-Aufbau im Frontend -- wird bewusst nicht in der DB normalisiert/
    # aufgeloest, das ist reine Anzeigelogik.
    references_header: Mapped[str | None] = mapped_column(Text)

    von_name: Mapped[str | None] = mapped_column(Text)
    von_adresse: Mapped[str | None] = mapped_column(Text)
    an: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cc: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    betreff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)

    datum: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gelesen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=False)
