import uuid

from sqlalchemy import Boolean, CheckConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Analog zu app/models/integration.py (MandantIntegration), nur ohne
# mandant_id -- gilt fuer die gesamte Plattform statt fuer einen einzelnen
# Mandanten. Aktuell nur "smtp" (globaler Mailversand-Fallback, siehe
# app/services/email_service.py); der Typ-Slot bleibt offen fuer
# zukuenftige plattformweite Integrationen, gleiches Muster wie bei
# MandantIntegration.
PLATTFORM_INTEGRATION_TYPEN = ("smtp",)


class PlattformIntegration(TimestampMixin, Base):
    __tablename__ = "plattform_integrationen"
    __table_args__ = (
        CheckConstraint(
            f"typ IN {PLATTFORM_INTEGRATION_TYPEN}", name="ck_plattform_integrationen_typ_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    typ: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
