import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muss mit der CHECK-Constraint aus Migration 0114 uebereinstimmen.
S3_LOESCHAUFTRAG_STATUS = ("offen", "erledigt", "fehler")


class S3Loeschauftrag(Base):
    """Objekte, die nach einem endgueltigen Loeschen (papierkorb_service.purge) aus dem
    Objektspeicher entfernt werden muessen. Der Auftrag entsteht in derselben
    Transaktion wie das DELETE (kein Objektverlust bei Rollback, kein Objekt-Waisen bei
    Absturz nach dem Commit); abgearbeitet wird nach dem Commit bzw. vom Worker."""

    __tablename__ = "s3_loeschauftraege"
    __table_args__ = (
        CheckConstraint(f"status IN {S3_LOESCHAUFTRAG_STATUS}", name="status_valid"),
        CheckConstraint("prefix LIKE '%/'", name="prefix_endet_mit_schraegstrich"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    anlass: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen", server_default="offen")
    versuche: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    naechster_versuch_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    letzter_fehler: Mapped[str | None] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    erledigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
