import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text
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
    """Die Kanban-Karte -- UND die private Aufgabe: projekt_id/spalte_id
    sind nullable, eine Zeile ohne Projekt ist eine private Aufgabe, fuer
    jeden Nutzer unabhaengig vom Rechte-Bereich "projekte" nutzbar (der
    ausschliesslich die Kanban-Funktion schuetzt, siehe
    app/api/routes/projekte.py). Sichtbarkeit privater Aufgaben ist auf
    zugewiesen_an/erstellt_von == aktueller Nutzer beschraenkt -- das ist
    keine RLS-Frage (Mandantentrennung bleibt unveraendert), sondern eine
    Anwendungsfall-Filterung in den Listen-Endpunkten.

    eltern_aufgabe_id (selbstreferenzierend) macht eine Zeile zur
    Unteraufgabe -- bewusst nur eine Ebene tief, Unteraufgaben von
    Unteraufgaben werden applikationsseitig abgelehnt. Eine Unteraufgabe
    einer Kanban-Aufgabe erscheint nicht als eigene Karte auf dem Board,
    nur im Detail-Panel der Elternaufgabe.

    anlage_id/kunde_id/standort_id sind wie vorgang_id rein referenzielle
    Schnellzugriffe, kein Status-Sync. erledigt_am ist der Abhak-Status fuer
    private Aufgaben/Unteraufgaben, die keine Kanban-Spalte haben.

    Reihenfolge innerhalb einer Spalte kommt bewusst ohne eigenes
    position-Feld aus -- Sortierung nach created_at, analog zum bestehenden
    Vorgaenge-Kanban (das ebenfalls nicht manuell umsortierbar ist, nur
    zwischen Spalten verschiebbar). checkliste/zusatzfelder sind JSONB und
    werden komplett ersetzt statt einzeln bearbeitet (gleiches Prinzip wie
    Board.inhalt_json oder MandantIntegration.config)."""

    __tablename__ = "projekt_aufgaben"
    __table_args__ = (
        CheckConstraint(
            f"prioritaet IN {PROJEKT_AUFGABE_PRIORITAETEN}", name="ck_projekt_aufgaben_prioritaet_valid"
        ),
        CheckConstraint(
            "spalte_id IS NULL OR projekt_id IS NOT NULL", name="ck_projekt_aufgaben_spalte_erfordert_projekt"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    projekt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id", ondelete="CASCADE"), nullable=True
    )
    spalte_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekt_spalten.id", ondelete="RESTRICT"), nullable=True
    )
    eltern_aufgabe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekt_aufgaben.id", ondelete="CASCADE"), nullable=True
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    faelligkeit_am: Mapped[date | None] = mapped_column(nullable=True)
    prioritaet: Mapped[str] = mapped_column(Text, nullable=False, default="mittel")
    zugewiesen_an: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Explizit timezone=True wie SoftDeleteMixin.geloescht_am -- wird direkt
    # aus Python mit datetime.now(UTC) befuellt (siehe
    # app/api/routes/projekte.py), ohne den expliziten Typ bindet asyncpg als
    # TIMESTAMP WITHOUT TIME ZONE und die Query schlaegt fehl.
    erledigt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Rein referenzielle, optionale Verknuepfungen -- kein Zwei-Wege-Status-
    # Sync in irgendeine Richtung (siehe app/api/routes/projekte.py).
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id", ondelete="SET NULL"), nullable=True
    )
    kunde_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id", ondelete="SET NULL"), nullable=True
    )
    standort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standorte.id", ondelete="SET NULL"), nullable=True
    )
    checkliste: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    zusatzfelder: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    erstellt_von: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
