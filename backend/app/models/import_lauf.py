import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Muessen mit den CHECK-Constraints aus Migration 0113 uebereinstimmen.
IMPORT_ENTITAETEN = ("kunden", "anlagen", "material")
IMPORT_STATUS = ("analysiert", "geprueft", "abgeschlossen", "abgebrochen", "rueckgaengig", "abgelaufen")
IMPORT_EINTRAG_TYPEN = ("kunde", "standort", "anlage", "pruefzyklus", "material")
IMPORT_EINTRAG_AKTIONEN = ("angelegt", "aktualisiert")


class ImportLauf(TimestampMixin, Base):
    """Nachweis je Datenimport (siehe docs/konzepte/DATENIMPORT.md). Die Quelldatei
    liegt nur bis zum Abschluss bzw. 24 h im Objektspeicher (object_key); Zuordnung
    und Optionen bleiben als Beleg stehen."""

    __tablename__ = "import_laeufe"
    __table_args__ = (
        CheckConstraint(f"entitaet IN {IMPORT_ENTITAETEN}", name="entitaet_valid"),
        CheckConstraint(f"status IN {IMPORT_STATUS}", name="status_valid"),
        CheckConstraint("format IN ('csv', 'xlsx')", name="format_valid"),
        Index("ix_import_laeufe_mandant_id_created_at", "mandant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    entitaet: Mapped[str] = mapped_column(Text, nullable=False)
    # Nur zur Anzeige (bereinigter Basisname), nie Teil eines Pfades oder Object-Keys.
    dateiname: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    dateigroesse: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    trennzeichen: Mapped[str | None] = mapped_column(Text)
    kodierung: Mapped[str | None] = mapped_column(Text)
    blatt: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="analysiert", server_default="analysiert")
    zeilen_gesamt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    zeilen_neu: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    zeilen_aktualisiert: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    zeilen_uebersprungen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    zeilen_fehler: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    zeilen_warnungen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    spalten: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    mapping: Mapped[dict | None] = mapped_column(JSONB)
    optionen: Mapped[dict | None] = mapped_column(JSONB)
    # Hash ueber Zuordnung + Optionen des letzten Probelaufs: der Import laeuft nur,
    # wenn exakt diese Konfiguration geprueft wurde.
    konfig_hash: Mapped[str | None] = mapped_column(Text)
    ergebnis: Mapped[dict | None] = mapped_column(JSONB)
    object_key: Mapped[str | None] = mapped_column(Text)
    fehlerbericht_key: Mapped[str | None] = mapped_column(Text)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    geprueft_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ausgefuehrt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rueckgaengig_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportLaufEintrag(Base):
    """ID eines durch einen Lauf angelegten oder aktualisierten Datensatzes --
    Grundlage fuer "Import rueckgaengig"."""

    __tablename__ = "import_lauf_eintraege"
    __table_args__ = (
        CheckConstraint(f"entitaet_typ IN {IMPORT_EINTRAG_TYPEN}", name="typ_valid"),
        CheckConstraint(f"aktion IN {IMPORT_EINTRAG_AKTIONEN}", name="aktion_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    import_lauf_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_laeufe.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entitaet_typ: Mapped[str] = mapped_column(Text, nullable=False)
    entitaet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    zeile: Mapped[int | None] = mapped_column(Integer)
