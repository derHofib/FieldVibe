import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

# Muessen mit den CHECK-Constraints aus Migration 0125 uebereinstimmen.
VOR_ORT_ROLLEN = ("mieter", "eigentuemer", "bauherr", "hausmeister", "nutzer", "sonstige")
VOR_ORT_QUELLEN = ("buero", "kundenportal", "telefonat")


class VorOrtKontakt(TimestampMixin, SoftDeleteMixin, Base):
    """Person auf der Seite von A's Kunden (Mieter, Bauherr, Hausmeister ...), die der Techniker vor Ort
    erreichen muss. Bewusst kein Kunde: kein Debitor, keine Kundennummer, kein Portal. Haengt am
    Auftraggeber (kunde_id), optional an einer Liegenschaft (standort_id). Anonymisiert statt geloescht,
    damit Verlauf und Statistik konsistent bleiben."""

    __tablename__ = "vor_ort_kontakte"
    __table_args__ = (
        CheckConstraint(f"rolle IN {VOR_ORT_ROLLEN}", name="rolle_valid"),
        CheckConstraint(f"quelle IS NULL OR quelle IN {VOR_ORT_QUELLEN}", name="quelle_valid"),
        CheckConstraint(
            "anonymisiert_am IS NOT NULL OR name IS NOT NULL OR telefon IS NOT NULL",
            name="name_oder_telefon",
        ),
        Index("ix_vor_ort_kontakte_mandant_kunde_standort", "mandant_id", "kunde_id", "standort_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    kunde_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False)
    standort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("standorte.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolle: Mapped[str] = mapped_column(Text, nullable=False)
    einheit: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefon: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefon2: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    erreichbarkeit: Mapped[str | None] = mapped_column(Text, nullable=True)
    hinweis: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Art. 14 DSGVO: woher die Daten stammen.
    quelle: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Wird beim Abschluss eines zugeordneten Vorgangs gesetzt; Grundlage der Anonymisierungsfrist.
    letzter_einsatz_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymisiert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    erstellt_von_kundenportal_zugang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kundenportal_zugaenge.id", name="fk_vor_ort_kontakte_portal_zugang_kundenportal_zugaenge"),
        nullable=True,
    )


class VorOrtKontaktZuordnung(Base):
    """Kontakt <-> genau ein Ziel (Projekt, Auftrag oder Vorgang). Drei FK-Spalten statt polymorphem Ziel,
    damit Postgres die Referenzen prueft und das Loeschen kaskadiert."""

    __tablename__ = "vor_ort_kontakt_zuordnungen"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(projekt_id, auftrag_id, vorgang_id) = 1",
            name="genau_ein_ziel",
        ),
        *(
            Index(
                f"uq_vor_ort_kontakt_zuordnungen_kontakt_{ziel}",
                "kontakt_id",
                ziel,
                unique=True,
                postgresql_where=text(f"{ziel} IS NOT NULL"),
            )
            for ziel in ("projekt_id", "auftrag_id", "vorgang_id")
        ),
        *(
            Index(
                f"uq_vor_ort_kontakt_zuordnungen_haupt_{ziel}",
                ziel,
                unique=True,
                postgresql_where=text(f"ist_hauptkontakt AND {ziel} IS NOT NULL"),
            )
            for ziel in ("projekt_id", "auftrag_id", "vorgang_id")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    kontakt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vor_ort_kontakte.id", ondelete="CASCADE"), nullable=False, index=True
    )
    projekt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projekte.id", ondelete="CASCADE"), nullable=True, index=True
    )
    auftrag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auftraege.id", ondelete="CASCADE"), nullable=True, index=True
    )
    vorgang_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ist_hauptkontakt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
