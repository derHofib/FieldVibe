import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

PROJEKT_AUFGABE_PRIORITAETEN = ("niedrig", "mittel", "hoch")


class Projekt(SoftDeleteMixin, TimestampMixin, Base):
    """Asana-artiges Kanban-Projekt fuer die Office-Oberflaeche -- eigene
    Aufgaben statt der bereits bestehenden, statusgetriebenen
    Vorgaenge-Kanban (siehe office/vorgaenge/VorgaengeKanban.tsx). Eine
    Aufgabe kann optional auf einen Vorgang verweisen (ProjektAufgabe.
    vorgang_id), ohne dass Projekte/Vorgaenge sonst irgendetwas
    miteinander zu tun haben."""

    __tablename__ = "projekte"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    archiviert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class ProjektSpalte(Base):
    """Frei benennbare/sortierbare Kanban-Spalte eines Projekts. Bewusst
    nicht papierkorbfaehig -- reine Konfiguration wie NavKategorie, kein
    fachlicher Inhalt. ON DELETE RESTRICT auf projekt_aufgaben.spalte_id
    verhindert, dass eine Spalte mit noch offenen Aufgaben verschwindet."""

    __tablename__ = "projekt_spalten"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjektAufgabe(SoftDeleteMixin, TimestampMixin, Base):
    """Die Kanban-Karte. Reihenfolge innerhalb einer Spalte kommt bewusst
    ohne eigenes position-Feld aus -- Sortierung nach created_at, analog zum
    bestehenden Vorgaenge-Kanban (das ebenfalls nicht manuell umsortierbar
    ist, nur zwischen Spalten verschiebbar). checkliste/zusatzfelder sind
    JSONB und werden komplett ersetzt statt einzeln bearbeitet (gleiches
    Prinzip wie Board.inhalt_json oder MandantIntegration.config)."""

    __tablename__ = "projekt_aufgaben"
    __table_args__ = (
        CheckConstraint(
            f"prioritaet IN {PROJEKT_AUFGABE_PRIORITAETEN}", name="ck_projekt_aufgaben_prioritaet_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    projekt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False
    )
    spalte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekt_spalten.id", ondelete="RESTRICT"), nullable=False
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    faelligkeit_am: Mapped[date | None] = mapped_column(nullable=True)
    prioritaet: Mapped[str] = mapped_column(Text, nullable=False, default="mittel")
    zugewiesen_an: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Rein referenzielle, optionale Verknuepfung zu einem bestehenden Vorgang
    # -- kein Zwei-Wege-Status-Sync (siehe app/api/routes/projekt_aufgaben.py).
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    checkliste: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    zusatzfelder: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
