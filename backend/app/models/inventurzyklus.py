import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class InventurZyklus(TimestampMixin, Base):
    """Wiederkehrende Bestandspruefung (Inventur) fuer einen Lagerort (eine
    Anlage mit objekttyp in fahrzeug/lager/baustelle) -- hoechstens ein
    Zyklus je Lagerort. aktiv=False deaktiviert/pausiert den Zyklus
    vollstaendig: er erscheint dann weder als Frist noch als Erinnerung."""

    __tablename__ = "inventurzyklen"
    __table_args__ = (
        CheckConstraint("intervall_tage > 0", name="ck_inventurzyklen_intervall_positiv"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    lager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=False, unique=True
    )
    intervall_tage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    letzte_inventur_am: Mapped[date | None] = mapped_column(Date)
    naechste_inventur_am: Mapped[date] = mapped_column(Date, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
