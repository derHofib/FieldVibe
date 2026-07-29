import uuid

from sqlalchemy import CheckConstraint, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Mandant(TimestampMixin, Base):
    __tablename__ = "mandanten"
    __table_args__ = (
        CheckConstraint(
            "status IN ('aktiv','pausiert','gekuendigt')", name="status_valid"
        ),
        CheckConstraint(
            "scheduler_stunde_utc IS NULL OR (scheduler_stunde_utc >= 0 AND scheduler_stunde_utc <= 23)",
            name="ck_mandanten_scheduler_stunde_utc_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    branche: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="aktiv")
    branding: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Nacharbeit (Abschnitt 12/4.5): NULL = globaler Default aus Settings
    # (scheduler_default_stunde_utc). Erlaubt einem Mandanten, den taeglichen
    # Pruefzyklen-/Mahnwesen-Lauf auf eine fuer den eigenen Betrieb passende
    # Uhrzeit zu legen, statt fest fuer alle Mandanten auf 03:00 UTC.
    scheduler_stunde_utc: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
