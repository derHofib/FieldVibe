import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muss mit den CHECK-Constraints aus Migration 0114 uebereinstimmen.
EXPORT_ARTEN = ("vollexport", "z3")
EXPORT_STATUS = ("wartend", "laeuft", "fertig", "fehler", "abgelaufen")


class MandantExport(Base):
    """Auftrag und Ergebnis eines asynchronen Mandanten-Exports (Vollexport, Z3). Das
    Ergebnis-ZIP liegt im Objektspeicher und wird nach laeuft_ab_am entfernt; die Zeile
    bleibt als Nachweis (wer, wann, welcher Hash)."""

    __tablename__ = "mandant_exporte"
    __table_args__ = (
        CheckConstraint(f"art IN {EXPORT_ARTEN}", name="art_valid"),
        CheckConstraint(f"status IN {EXPORT_STATUS}", name="status_valid"),
        # Hoechstens ein wartender oder laufender Export je Mandant (Rate-Limit in der DB).
        Index(
            "uq_mandant_exporte_ein_aktiver",
            "mandant_id",
            unique=True,
            postgresql_where=text("status IN ('wartend', 'laeuft')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    art: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="wartend", server_default="wartend")
    parameter: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    angefordert_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    angefordert_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    gestartet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fertig_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    laeuft_ab_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    object_key: Mapped[str | None] = mapped_column(Text)
    groesse_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    anzahl_dateien: Mapped[int | None] = mapped_column(Integer)
    fehler: Mapped[str | None] = mapped_column(Text)
