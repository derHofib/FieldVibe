import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

GESPEICHERTER_FILTER_ENTITAETEN = ("vorgaenge", "anlagen", "kunden", "standorte", "rechnungen")


class GespeicherterFilter(TimestampMixin, Base):
    """Eine vom Nutzer benannte Filter-Vorlage (z.B. "Meine offenen Störungen")
    fuer eine der Listenansichten -- personenbezogen (nicht mandantenweit
    geteilt), damit sich jeder seine eigenen Vorlagen einrichten kann. Je
    Nutzer und Entitaet kann genau eine Vorlage als Standard markiert sein
    (siehe app/api/routes/gespeicherte_filter.py), die dann beim Oeffnen der
    jeweiligen Liste automatisch angewendet wird."""

    __tablename__ = "gespeicherte_filter"
    __table_args__ = (
        UniqueConstraint("user_id", "entitaet", "name", name="uq_gespeicherte_filter_user_entitaet_name"),
        CheckConstraint(
            f"entitaet IN {GESPEICHERTER_FILTER_ENTITAETEN}", name="ck_gespeicherte_filter_entitaet_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    entitaet: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    filter_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ist_standard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
