import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Mandant(TimestampMixin, Base):
    __tablename__ = "mandanten"
    __table_args__ = (
        CheckConstraint(
            "status IN ('aktiv','pausiert','gekuendigt')", name="status_valid"
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
