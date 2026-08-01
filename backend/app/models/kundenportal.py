import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KundenportalZugang(TimestampMixin, Base):
    __tablename__ = "kundenportal_zugaenge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Personalisierter Login-Link (/portal/l/{login_slug}): identifiziert nur,
    # wer sich anmeldet und befuellt die E-Mail auf der Login-Seite vor --
    # ersetzt NICHT die Passwort-Eingabe (siehe app/api/routes/kundenportal_auth.py).
    login_slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
