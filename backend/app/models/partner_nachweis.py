import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Rechtlich/kaufmaennisch relevante Nachweise eines Nachunternehmers, jeweils
# mit optionalem Ablaufdatum -- dasselbe Ueberwachungsmuster wie
# Pruefmittel.naechste_kalibrierung_am, nur fuer Vertragsunterlagen statt
# Messgeraete. "freistellungsbescheinigung" ist der wichtigste Fall: fehlt
# sie oder ist sie abgelaufen, muss der Mandant nach § 48 EStG 15%
# Bauabzugsteuer von Partner-Rechnungen einbehalten (siehe
# app/services/partner_service.py).
PARTNER_NACHWEIS_TYPEN = (
    "freistellungsbescheinigung",
    "haftpflichtversicherung",
    "gewerbeanmeldung",
    "handwerksrolle",
    "avv_dsgvo",
    "sonstiges",
)


class PartnerNachweis(TimestampMixin, Base):
    __tablename__ = "partner_nachweise"
    __table_args__ = (
        CheckConstraint(
            f"typ IN {PARTNER_NACHWEIS_TYPEN}", name="ck_partner_nachweise_typ_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner.id", ondelete="CASCADE"), nullable=False
    )
    typ: Mapped[str] = mapped_column(Text, nullable=False)
    gueltig_bis: Mapped[date | None] = mapped_column(Date)
    dokument_s3_key: Mapped[str | None] = mapped_column(Text)
    notiz: Mapped[str | None] = mapped_column(Text)
