import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.rechte_registry import SCOPES
from app.db.base import Base, TimestampMixin

ORG_EINHEIT_TYPEN = ("bereich", "abteilung", "team")
POSITION_TYPEN = ("linie", "stabsstelle")
BESETZUNG_ARTEN = ("regulaer", "vertretung")
RECHT_WIRKUNGEN = ("erlauben", "verweigern")


class OrgEinheit(TimestampMixin, Base):
    __tablename__ = "org_einheiten"
    __table_args__ = (
        CheckConstraint(f"typ IN {ORG_EINHEIT_TYPEN}", name="typ_valid"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_nicht_selbst"),
        Index("ix_org_einheiten_mandant_parent", "mandant_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    typ: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_einheiten.id", ondelete="RESTRICT"), nullable=True
    )
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Position(TimestampMixin, Base):
    """Knoten im Organigramm (Stelle, nicht Person). Status ist abgeleitet:
    besetzt (aktive Besetzung) / vakant (keine) / geplant (Flag)."""

    __tablename__ = "positionen"
    __table_args__ = (
        CheckConstraint(f"typ IN {POSITION_TYPEN}", name="typ_valid"),
        CheckConstraint("soll_besetzung >= 0", name="soll_besetzung_nicht_negativ"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_nicht_selbst"),
        Index("ix_positionen_mandant_parent", "mandant_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positionen.id", ondelete="RESTRICT"), nullable=True
    )
    typ: Mapped[str] = mapped_column(Text, nullable=False, default="linie", server_default="linie")
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    ebene: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_einheit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_einheiten.id"), nullable=True
    )
    account_typ_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_typen.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    geplant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    soll_besetzung: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    gueltig_ab: Mapped[date | None] = mapped_column(Date, nullable=True)
    gueltig_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class PositionBesetzung(TimestampMixin, Base):
    """Historie + Mehrfachbesetzung + Vertretung: aktiv = gueltig_bis IS NULL."""

    __tablename__ = "position_besetzungen"
    __table_args__ = (
        CheckConstraint(f"art IN {BESETZUNG_ARTEN}", name="art_valid"),
        CheckConstraint("gueltig_bis IS NULL OR gueltig_bis > gueltig_von", name="zeitraum_valid"),
        Index(
            "uq_position_besetzungen_aktiv",
            "position_id",
            "user_id",
            unique=True,
            postgresql_where=text("gueltig_bis IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positionen.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    art: Mapped[str] = mapped_column(Text, nullable=False, default="regulaer", server_default="regulaer")
    gueltig_von: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    gueltig_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PositionRecht(TimestampMixin, Base):
    """Override auf einer Position gegenueber der Account-Typ-Basis."""

    __tablename__ = "position_rechte"
    __table_args__ = (
        UniqueConstraint("position_id", "bereich", "aktion", name="uq_position_rechte_ziel"),
        CheckConstraint(f"wirkung IN {RECHT_WIRKUNGEN}", name="wirkung_valid"),
        CheckConstraint(f"scope IS NULL OR scope IN {SCOPES}", name="scope_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positionen.id", ondelete="CASCADE"), nullable=False
    )
    bereich: Mapped[str] = mapped_column(Text, nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    wirkung: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserRecht(TimestampMixin, Base):
    """Override je Nutzer; "verweigern" gilt global (Deny schlaegt Allow)."""

    __tablename__ = "user_rechte"
    __table_args__ = (
        UniqueConstraint("user_id", "bereich", "aktion", name="uq_user_rechte_ziel"),
        CheckConstraint(f"wirkung IN {RECHT_WIRKUNGEN}", name="wirkung_valid"),
        CheckConstraint(f"scope IS NULL OR scope IN {SCOPES}", name="scope_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    bereich: Mapped[str] = mapped_column(Text, nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    wirkung: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
