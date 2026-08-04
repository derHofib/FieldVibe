import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin
from app.models.vorgang import LEISTUNGSTYPEN

VORGANG_ANFRAGE_STATUS = ("offen", "angenommen", "abgelehnt")


class VorgangAnfrage(SoftDeleteMixin, TimestampMixin, Base):
    """Ein vom Kunden ueber das Kundenportal gestellter Auftragswunsch. Wird
    erst durch die Annahme eines Mitarbeiters (siehe
    app/api/routes/vorgang_anfragen.py) zu einem echten Vorgang -- so bleiben
    Vorgang.abrechnungsart & Co. weiterhin ausschliesslich interne
    Entscheidungen."""

    __tablename__ = "vorgang_anfragen"
    __table_args__ = (
        CheckConstraint(
            f"status IN {VORGANG_ANFRAGE_STATUS}", name="ck_vorgang_anfragen_status_valid"
        ),
        CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}", name="ck_vorgang_anfragen_leistungstyp_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    kundenportal_zugang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kundenportal_zugaenge.id"), nullable=False
    )
    standort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standorte.id"), nullable=True
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    ablehnungsgrund: Mapped[str | None] = mapped_column(Text)
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    bearbeitet_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    bearbeitet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
