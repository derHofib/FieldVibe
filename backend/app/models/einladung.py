import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

EINLADUNG_ARTEN = ("mitarbeiter", "kunde", "partner")
EINLADUNG_ROLLEN = ("mandant_admin", "custom")
EINLADUNG_STATUS = ("offen", "angenommen", "widerrufen")


class Einladung(TimestampMixin, Base):
    """Ersetzt das direkte Anlegen eines Accounts mit einem vom Admin
    vergebenen Passwort: der eingeladene Mensch registriert sich selbst
    (siehe app/services/einladung_service.py und die drei
    *_registrieren-Endpunkte in auth.py/kundenportal_auth.py/
    partner_auth.py). Der eigentliche User-/KundenportalZugang-/
    PartnerZugang-Datensatz entsteht erst bei Annahme, nicht schon hier."""

    __tablename__ = "einladungen"
    __table_args__ = (
        CheckConstraint(f"art IN {EINLADUNG_ARTEN}", name="ck_einladungen_art_valid"),
        CheckConstraint(
            f"rolle IS NULL OR rolle IN {EINLADUNG_ROLLEN}", name="ck_einladungen_rolle_valid"
        ),
        CheckConstraint(f"status IN {EINLADUNG_STATUS}", name="ck_einladungen_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    art: Mapped[str] = mapped_column(Text, nullable=False)
    rolle: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_typ_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_typen.id"), nullable=True
    )
    kunde_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id", ondelete="CASCADE"), nullable=True
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    eingeladen_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    angenommen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
