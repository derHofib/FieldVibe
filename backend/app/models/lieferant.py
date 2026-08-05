import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class Lieferant(SoftDeleteMixin, TimestampMixin, Base):
    """Stammdaten eines Großhändlers/Lieferanten, an den eine Bestellung
    (siehe app/models/bestellung.py) adressiert wird. Bewusst schlank
    gehalten (kein eigenes Adressfeld) -- der einzige heute benoetigte Zweck
    ist Name + Kontakt fuer den Bestell-Export/-Versand. Kuenftige
    API-Zugangsdaten fuer eine direkte Großhaendler-Anbindung wuerden hier
    ergaenzt, nach demselben Verschluesselungsmuster wie
    app/models/integration.py."""

    __tablename__ = "lieferanten"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    telefon: Mapped[str | None] = mapped_column(Text)
    notiz: Mapped[str | None] = mapped_column(Text)
