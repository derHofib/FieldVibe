import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

# Muss mit der CHECK-Constraint ck_zeiterfassung_buchungsstatus_valid
# (Migration 0084) uebereinstimmen. Nur fuer Eintraege MIT vorgang_id
# relevant -- Urlaub/Krankheit/etc. ohne Vorgang bleiben dauerhaft
# 'vermerkt' (siehe docs/konzepte/ZEITERFASSUNG.md, Abschnitt 5.1).
ZEITERFASSUNG_BUCHUNGSSTATUS = ("vermerkt", "vorgemerkt", "gebucht", "abgerechnet")

# "auftrag" ist die einzige Kategorie, die der Start/Stop-Timer selbst
# vergibt (siehe start_timer in app/api/routes/zeiterfassung.py) -- alle
# anderen sind nur ueber die manuelle Erfassung erreichbar und haben
# absichtlich kein Pflicht-vorgang_id (siehe Migration 0050).
ZEITERFASSUNG_KATEGORIEN = (
    "auftrag",
    "verwaltung",
    "fahrzeit",
    "schulung",
    "pause",
    "urlaub",
    "krankheit",
    "sonstiges",
)


class Zeiterfassung(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "zeiterfassung"
    __table_args__ = (
        CheckConstraint(
            f"kategorie IN {ZEITERFASSUNG_KATEGORIEN}", name="ck_zeiterfassung_kategorie_valid"
        ),
        CheckConstraint(
            f"buchungsstatus IN {ZEITERFASSUNG_BUCHUNGSSTATUS}",
            name="ck_zeiterfassung_buchungsstatus_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    # Nullable seit Migration 0050 -- nur noch Auftragszeit (Timer oder
    # manuell nachgetragen mit Vorgangsbezug) hat einen Vorgang, Urlaub/
    # Krankheit/Verwaltung/etc. nicht.
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=True
    )
    techniker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ende_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    taetigkeit: Mapped[str | None] = mapped_column(Text)
    abrechenbar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    kategorie: Mapped[str] = mapped_column(Text, nullable=False, default="auftrag")
    # Optionaler Stundenverrechnungssatz aus dem Leistungsverzeichnis des
    # Kunden -- koppelt diese Zeiterfassung an einen Preis, ohne den
    # Automatismus zu erzwingen (Start/Stop-Timer setzt ihn nie, nur die
    # manuelle Erfassung/nachtraegliches PATCH).
    lv_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leistungsverzeichnis_positionen.id"),
        nullable=True,
    )
    # Buchungsablauf (Stufe 2, docs/konzepte/ZEITERFASSUNG.md Abschnitt 6.1):
    # vermerkt -> vorgemerkt -> gebucht -> abgerechnet, mit definierten
    # Ruecktritten. Aendert sich nur ueber die Buchungs-Endpunkte, nie per
    # PATCH (siehe app/api/routes/zeiterfassung.py).
    buchungsstatus: Mapped[str] = mapped_column(Text, nullable=False, default="vermerkt")
    vorgemerkt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    vorgemerkt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gebucht_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    gebucht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
