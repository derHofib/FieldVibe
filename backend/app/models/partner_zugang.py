import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PartnerZugang(TimestampMixin, Base):
    """Login-Credentials fuers Partnerportal -- spiegelt KundenportalZugang
    exakt (eigene Identitaetsraum, eigener Token-Typ, siehe
    app/core/security.py und app/api/deps.py)."""

    __tablename__ = "partner_zugaenge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
