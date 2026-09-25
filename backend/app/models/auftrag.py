import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

AUFTRAG_STATUS = ("offen", "in_arbeit", "abgeschlossen", "storniert")


class Auftrag(SoftDeleteMixin, TimestampMixin, Base):
    """Buendelt mehrere Vorgaenge zu einem Kundenauftrag -- Ebene zwischen
    Projekt und Vorgang: Projekt --* Auftrag --* Vorgang, wobei ein Vorgang
    weiterhin auch ohne Auftrag direkt an einem Projekt haengen kann
    (Vorgang.projekt_id bleibt unabhaengig davon bestehen, siehe
    app/models/vorgang.py). projekt_id und kunde_id sind beide optional --
    ein Auftrag muss keinem Projekt zugeordnet sein.

    Rein referenziell wie Projekt.vertrag_id/Vorgang.projekt_id: kein
    Status-Sync mit den zugehoerigen Vorgaengen. Nutzt bewusst den
    bestehenden Rechte-Bereich "projekte" (app/models/account_typ.py) statt
    eines eigenen -- Auftrag ist organisatorisch eng an Projekt angelehnt,
    ein eigener Bereich haette nur die Rechte-Matrix aufgeblaeht."""

    __tablename__ = "auftraege"
    __table_args__ = (
        CheckConstraint(f"status IN {AUFTRAG_STATUS}", name="ck_auftraege_status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    projekt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id"), nullable=True
    )
    kunde_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=True
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="offen")
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
