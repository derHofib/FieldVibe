import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class JobLauf(TimestampMixin, Base):
    """Zustand eines Hintergrundjobs: je (job, mandant_id) der Zeitpunkt des
    letzten erfolgreichen Laufs. mandant_id NULL = systemweiter Job bzw. Heartbeat
    (worker_tick, mail_sync). Quelle der Wahrheit dafuer, was der Worker
    nachholen muss -- nicht der Timer."""

    __tablename__ = "job_laeufe"
    __table_args__ = (
        Index(
            "uq_job_laeufe_job_mandant", "job", "mandant_id",
            unique=True, postgresql_where=text("mandant_id IS NOT NULL"),
        ),
        Index("uq_job_laeufe_job_system", "job", unique=True, postgresql_where=text("mandant_id IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job: Mapped[str] = mapped_column(Text, nullable=False)
    mandant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id", ondelete="CASCADE"), nullable=True
    )
    letzter_versuch_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letzter_lauf_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letzter_fehler: Mapped[str | None] = mapped_column(Text)
    fehler_in_folge: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ergebnis: Mapped[dict | None] = mapped_column(JSONB)
