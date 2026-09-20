import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class VorgangAbhaengigkeit(Base):
    """"vorgang_id ist blockiert von blockiert_von_id" -- z.B. eine
    Teilleistung kann erst starten, wenn eine andere abgeschlossen ist.
    Bewusst ohne TimestampMixin/updated_at wie ProjektSpalte: eine reine
    Verknuepfungszeile wird bei Aenderung geloescht/neu angelegt statt
    upgedatet, siehe app/api/routes/vorgaenge.py.

    Zyklen (A blockiert B blockiert A) werden applikationsseitig geprueft,
    nicht per DB-Constraint -- ein CHECK kann keine transitiven Pfade
    pruefen. Gegen mandantenuebergreifende Verknuepfungen schuetzt bereits
    die RLS-gescopte Session: ein session.get(Vorgang, ...) auf einen
    fremden Vorgang liefert None, siehe _vorgang_abhaengigkeit_anlegen()."""

    __tablename__ = "vorgang_abhaengigkeiten"
    __table_args__ = (
        CheckConstraint("vorgang_id <> blockiert_von_id", name="ck_vorgang_abhaengigkeiten_nicht_selbst"),
        UniqueConstraint("vorgang_id", "blockiert_von_id", name="uq_vorgang_abhaengigkeiten_paar"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=False
    )
    blockiert_von_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=False
    )
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
