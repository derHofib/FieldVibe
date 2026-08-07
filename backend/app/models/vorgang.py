import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

ABRECHNUNGSARTEN_VORGANG = (
    "pauschale",
    "aufwand",
    "festpreis",
    "wartungsvertrag",
    "gewaehrleistung",
)
LEISTUNGSTYPEN = ("installation", "pruefung", "wartung", "stoerung", "beratung", "planung")
VORGANG_STATUS = (
    "neu",
    "geplant",
    "in_arbeit",
    "wartet_kunde",
    "abgeschlossen",
    "abgerechnet",
    "storniert",
)


class Vorgang(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "vorgaenge"
    __table_args__ = (
        UniqueConstraint(
            "mandant_id", "vorgangsnummer", name="uq_vorgaenge_mandant_vorgangsnummer"
        ),
        UniqueConstraint("client_uuid", name="uq_vorgaenge_client_uuid"),
        CheckConstraint(
            f"abrechnungsart IN {ABRECHNUNGSARTEN_VORGANG}",
            name="ck_vorgaenge_abrechnungsart_valid",
        ),
        CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}", name="ck_vorgaenge_leistungstyp_valid"
        ),
        CheckConstraint(f"status IN {VORGANG_STATUS}", name="ck_vorgaenge_status_valid"),
        Index("idx_vorgaenge_feed", "mandant_id", "last_activity_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    vorgangsnummer: Mapped[str] = mapped_column(Text, nullable=False)
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    anlage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("anlagen.id"), nullable=True
    )
    standort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standorte.id"), nullable=True
    )
    vertrag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vertraege.id"), nullable=True
    )
    parent_vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id"), nullable=True
    )
    dauerauftrag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dauerauftraege.id"), nullable=True
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    abrechnungsart: Mapped[str] = mapped_column(Text, nullable=False)
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="neu")
    prioritaet: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Von der Offline-Outbox vergebene Idempotenz-ID (Nacharbeit): erlaubt
    # einen sicheren Sync-Retry der Neuanlage eines Vorgangs, ohne bei
    # doppeltem Versand versehentlich zwei Vorgaenge zu erzeugen -- exakt
    # dasselbe Muster wie VorgangEvent.client_uuid.
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Ansprechpartner beim Kunden, falls dieser Vorgang aus einer per
    # Kundenportal gestellten und angenommenen Auftragsanfrage entstanden ist
    # (siehe app/models/vorgang_anfrage.py). NULL bei intern erstellten
    # Vorgaengen.
    erstellt_von_kundenportal_zugang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kundenportal_zugaenge.id"), nullable=True
    )
    # Mitarbeiter, der den Vorgang angelegt hat -- NULL bei Vorgaengen aus
    # einer Kundenportal-Anfrage (siehe erstellt_von_kundenportal_zugang_id
    # oben) oder bei sehr alten, vor Einfuehrung dieses Felds erstellten
    # Vorgaengen.
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Faelligkeitsdatum, ueber das Aufträge im Feed/Filter priorisiert werden
    # koennen -- optional, da nicht jeder Vorgang eine feste Frist hat.
    faelligkeit_am: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Adresse direkt am Vorgang, falls kein Standort angelegt werden soll
    # (z.B. einmaliger Auftrag) -- der Ausfuehrende muss trotzdem wissen,
    # wo er hin muss.
    adresse: Mapped[dict | None] = mapped_column(JSONB)
    # Wer ist gerade fuer diesen Vorgang zustaendig -- per Selbst-Zuweisung
    # ("Ticket übernehmen", siehe app/api/routes/vorgaenge.py:uebernehmen) oder
    # manuell per PATCH durch mandant_admin/Dispo gesetzt. NULL = unzugewiesen.
    zugewiesener_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
