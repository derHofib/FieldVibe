import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ROLES = (
    "super_admin",
    "mandant_admin",
    "disponent",
    "techniker",
    "controller",
    "mitarbeiter",
    # Papierkorb (siehe app/services/papierkorb_service.py): loesch_ansicht
    # sieht ausschliesslich den Papierkorb (rein lesend), loesch_operativ hat
    # zusaetzlich ueberall dieselben Rechte wie mandant_admin (siehe
    # app/api/deps.py:require_roles()) und darf zudem loeschen/
    # wiederherstellen/endgueltig loeschen. Beide Rollen sind nur durch
    # super_admin vergebbar (siehe app/api/routes/users.py), von
    # loesch_operativ darf es je Mandant hoechstens einen aktiven Account
    # geben (siehe Migration 0032, partial unique index).
    "loesch_ansicht",
    "loesch_operativ",
)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="role_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
