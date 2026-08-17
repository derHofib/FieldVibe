import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EMAIL_ENTITY_TYPEN = ("kunde", "vorgang", "angebot", "rechnung", "bestellung")
EMAIL_STATUS = ("gesendet", "fehler")


class EmailLog(Base):
    """Protokoll aller aus FieldVibe heraus versendeten E-Mails -- reines
    Log, unveraenderlich nach dem Anlegen. entity_type/entity_id verweisen
    auf das Kunde/Vorgang/Angebot/Rechnung/Bestellung, von dem aus die Mail
    verschickt wurde, damit sie dort im Verlauf angezeigt werden kann."""

    __tablename__ = "email_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    empfaenger: Mapped[str] = mapped_column(Text, nullable=False)
    betreff: Mapped[str] = mapped_column(Text, nullable=False)
    inhalt: Mapped[str] = mapped_column(Text, nullable=False)
    anhang_dateiname: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    fehlermeldung: Mapped[str | None] = mapped_column(Text)
    # NULL bei automatisch vom Mahnwesen-Scheduler versendeten Mahnungen --
    # es gibt dabei keinen handelnden Nutzer (analog zu
    # AuditLog.actor_user_id bei Scheduler-Laeufen).
    gesendet_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
