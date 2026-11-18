import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KiClient(Base):
    """Per Dynamic Client Registration angelegter OAuth-Client (z. B. Claude).
    Mandantenlos und ohne RLS: die Registrierung erfolgt vor jedem Login
    (Migration 0118)."""

    __tablename__ = "ki_clients"

    client_id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Vollstaendiges OAuthClientInformationFull des MCP-SDK als JSON.
    client_info: Mapped[dict] = mapped_column(JSONB, nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KiVerbindung(Base):
    """Eine vom Nutzer erteilte KI-Einwilligung (Nutzer + Client + Scopes) und
    Anker fuer Widerruf und Refresh-Rotation."""

    __tablename__ = "ki_verbindungen"
    __table_args__ = (
        Index("ix_ki_verbindungen_mandant_id", "mandant_id"),
        Index("ix_ki_verbindungen_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(Text, ForeignKey("ki_clients.client_id"), nullable=False)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    code_eingeloest_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_jti: Mapped[str | None] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    zuletzt_genutzt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    widerrufen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
