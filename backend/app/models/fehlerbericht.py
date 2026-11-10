import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

FEHLERBERICHT_STATUS = ("neu", "gesichtet", "in_arbeit", "behoben", "abgelehnt", "duplikat")
FEHLERBERICHT_ARTEN = ("fehler", "idee")
FEHLERBERICHT_SCHWEREGRADE = ("niedrig", "mittel", "hoch", "blockierend")
# Erledigt = kein Kandidat mehr fuer die Duplikat-Erkennung.
FEHLERBERICHT_ERLEDIGT_STATUS = ("behoben", "abgelehnt", "duplikat")


class Fehlerbericht(Base):
    __tablename__ = "fehlerberichte"
    __table_args__ = (
        CheckConstraint(f"schweregrad IN {FEHLERBERICHT_SCHWEREGRADE}", name="schweregrad_valid"),
        CheckConstraint(f"status IN {FEHLERBERICHT_STATUS}", name="status_valid"),
        CheckConstraint(f"art IN {FEHLERBERICHT_ARTEN}", name="art_valid"),
        Index("ix_fehlerberichte_art_status", "art", "status"),
        Index("ix_fehlerberichte_mandant_status", "mandant_id", "status"),
        Index("ix_fehlerberichte_fingerprint", "fingerprint"),
        Index("ix_fehlerberichte_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    art: Mapped[str] = mapped_column(Text, nullable=False, default="fehler", server_default="fehler")
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, nullable=False)
    erwartet: Mapped[str | None] = mapped_column(Text, nullable=True)
    schritte: Mapped[str | None] = mapped_column(Text, nullable=True)
    schweregrad: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="neu", server_default="neu")
    kontext: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # S3-Keys, keine URLs -- presigned URLs werden erst beim Lesen erzeugt.
    screenshot_original_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_annotiert_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplikat_von_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fehlerberichte.id", ondelete="SET NULL"), nullable=True
    )
    loesungsnotiz: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_commit: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    erledigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nur bei art='idee': Zeitpunkt, an dem der Super-Admin sie freigegeben hat.
    freigegeben_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Explizit timezone=True statt TimestampMixin: Aufbewahrungsjob und
    # seit-Filter vergleichen mit tz-aware datetimes (asyncpg lehnt sie sonst
    # fuer TIMESTAMP WITHOUT TIME ZONE ab).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
