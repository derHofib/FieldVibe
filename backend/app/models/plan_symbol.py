"""Mandanten-eigene Symbol-Bibliothek fuer den Feldtyp "foto_plan" (siehe
Migration 0081 fuer die Begruendung, warum das eine eigene Tabelle statt
eines festen Code-Katalogs ist). object_key verweist wie bei anderen
Datei-Uploads (siehe storage_service.py) auf ein Objekt im selben S3/
MinIO-Bucket."""
import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PlanSymbol(TimestampMixin, Base):
    __tablename__ = "plan_symbole"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
