import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Muessen mit den CHECK-Constraints aus Migration 0128 uebereinstimmen.
KI_AKTION_STATUS = ("ausgefuehrt", "vorgeschlagen", "abgelehnt", "verfallen", "fehlgeschlagen", "rueckgaengig")
KI_REGEL_MODI = ("direkt", "chat", "fieldvibe", "vier_augen", "aus")


def _leere_liste() -> Mapped[list]:
    return mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))


class KiAktion(Base):
    """Journal einer KI-Aktion (MCP): wer hat was ueber welche Verbindung getan, mit Vorher/Nachher und dem
    Rueckweg fuer das Rueckgaengig. Bewusst getrennt vom Audit-Log (GoBD-Hash-Kette, unveraenderlich)."""

    __tablename__ = "ki_aktionen"
    __table_args__ = (
        CheckConstraint("stufe BETWEEN 1 AND 3", name="stufe_valid"),
        CheckConstraint(f"status IN {KI_AKTION_STATUS}", name="status_valid"),
        Index("ix_ki_aktionen_mandant_erstellt", "mandant_id", text("erstellt_am DESC")),
        Index("ix_ki_aktionen_mandant_user_erstellt", "mandant_id", "user_id", text("erstellt_am DESC")),
        Index(
            "ix_ki_aktionen_vorschlag_gueltig",
            "status",
            "gueltig_bis",
            postgresql_where=text("status = 'vorgeschlagen'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ki_verbindung_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ki_verbindungen.id", ondelete="SET NULL"), nullable=True
    )
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    aktionsart: Mapped[str] = mapped_column(Text, nullable=False)
    stufe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    zusammenfassung: Mapped[str] = mapped_column(Text, nullable=False)
    ziele: Mapped[list] = _leere_liste()
    aenderungen: Mapped[list] = _leere_liste()
    erzeugt: Mapped[list] = _leere_liste()
    rueckweg: Mapped[list] = _leere_liste()
    eingabe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vorschau: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    inhalt_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    modus: Mapped[str | None] = mapped_column(Text, nullable=True)
    gueltig_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bestaetigt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    bestaetigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bestaetigt_via: Mapped[str | None] = mapped_column(Text, nullable=True)
    rueckgaengig_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rueckgaengig_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rueckgaengig_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    fehler: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KiRegel(Base):
    """Modus und Tageslimit je Aktionsart und Mandant (ab Etappe B; fehlende Zeile = Vorgabe aus dem Code)."""

    __tablename__ = "ki_regeln"
    __table_args__ = (
        PrimaryKeyConstraint("mandant_id", "aktionsart", name="pk_ki_regeln"),
        CheckConstraint(f"modus IN {KI_REGEL_MODI}", name="modus_valid"),
        CheckConstraint("tageslimit IS NULL OR tageslimit >= 0", name="tageslimit_nicht_negativ"),
    )

    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id", ondelete="CASCADE"), nullable=False
    )
    aktionsart: Mapped[str] = mapped_column(Text, nullable=False)
    modus: Mapped[str] = mapped_column(Text, nullable=False)
    tageslimit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geaendert_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    geaendert_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
