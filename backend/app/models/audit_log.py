import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muss mit der CHECK-Constraint aus Migration 0114 uebereinstimmen.
AKTEUR_TYPEN = ("user", "portal", "system", "partner")


class AuditLog(Base):
    """Append-only (DB-Trigger, Migration 0114). Mandantenbezogene Eintraege
    werden kurz vor dem COMMIT in audit_log_siegel verkettet."""

    __tablename__ = "audit_log"
    __table_args__ = (CheckConstraint(f"akteur_typ IN {AKTEUR_TYPEN}", name="akteur_typ_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mandant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    akteur_typ: Mapped[str] = mapped_column(Text, nullable=False, default="user", server_default="user")
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(Text)
    # Gekuerzt (siehe audit_service.ip_kuerzen), nicht die volle Adresse.
    ip: Mapped[str | None] = mapped_column(Text)
    # True fuer Zeilen aus der Zeit vor der Hash-Kette: ohne Siegel erwartet.
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLogSiegel(Base):
    __tablename__ = "audit_log_siegel"
    __table_args__ = (
        UniqueConstraint("mandant_id", "seq"),
        UniqueConstraint("audit_log_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    audit_log_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("audit_log.id"), nullable=False)
    vorgaenger_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
