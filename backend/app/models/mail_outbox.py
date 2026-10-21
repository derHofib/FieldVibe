import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Muessen mit dem CHECK-Constraint aus Migration 0115 uebereinstimmen.
OUTBOX_STATUS = ("pending", "sending", "sent", "failed")


class MailOutbox(TimestampMixin, Base):
    """Warteschlange fuer ausgehende Mails (siehe app/services/mail_outbox_service.py).
    Die Zeile entsteht in der Transaktion der ausloesenden Aktion; versendet wird
    erst nach deren Commit durch den Worker. anhaenge: Liste aus
    {dateiname, mimetype, s3_key} -- die Bytes liegen im Objektspeicher."""

    __tablename__ = "mail_outbox"
    __table_args__ = (
        CheckConstraint(f"status IN {OUTBOX_STATUS}", name="status_valid"),
        Index("ix_mail_outbox_faellig", "naechster_versuch_am", postgresql_where=text("status = 'pending'")),
        Index("ix_mail_outbox_mandant_id_status", "mandant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"))
    email_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_log.id", ondelete="SET NULL")
    )
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    empfaenger: Mapped[str] = mapped_column(Text, nullable=False)
    betreff: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text)
    anhaenge: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default="pending")
    versuche: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    naechster_versuch_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sending_seit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letzter_fehler: Mapped[str | None] = mapped_column(Text)
    gesendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
