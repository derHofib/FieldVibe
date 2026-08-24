import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NavKategorie(TimestampMixin, Base):
    """Mandanten-eigene Kategorie fuer die Office-Seitenleiste (siehe
    frontend/src/config/navSeiten.ts). Ein Mandant ohne eigene Zeilen hier
    hat die vier hart codierten Standardkategorien noch nie angefasst --
    das Frontend faellt dann direkt auf sie zurueck."""

    __tablename__ = "nav_kategorien"
    __table_args__ = (UniqueConstraint("mandant_id", "name", name="uq_nav_kategorien_mandant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False)


class NavZuordnung(Base):
    """Ordnet einen einzelnen Menuepunkt (nav_key aus navSeiten.ts) einer
    NavKategorie dieses Mandanten zu. ON DELETE RESTRICT auf kategorie_id --
    eine Kategorie mit noch zugeordneten Punkten kann nicht geloescht
    werden (das PUT in nav_kategorien.py raeumt Zuordnungen vor dem
    Loeschen ohnehin immer leer, das ist nur ein zusaetzliches Sicherheitsnetz)."""

    __tablename__ = "nav_zuordnungen"
    __table_args__ = (UniqueConstraint("mandant_id", "nav_key", name="uq_nav_zuordnungen_mandant_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    nav_key: Mapped[str] = mapped_column(Text, nullable=False)
    kategorie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nav_kategorien.id", ondelete="RESTRICT"), nullable=False
    )
