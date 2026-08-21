import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Partner(TimestampMixin, Base):
    """Ein Nachunternehmer/Subunternehmer, dem einzelne Vorgaenge (komplett
    oder als Teilleistung ueber einen Kind-Vorgang, siehe
    Vorgang.parent_vorgang_id) delegiert werden koennen. Mandantengebunden
    wie Kunde -- dieselbe reale Firma, die fuer mehrere Mandanten arbeitet,
    bekommt bei jedem einen eigenen Partner-Datensatz und eigenen
    Portal-Zugang, kein geteiltes Login ueber Mandanten hinweg (siehe
    app/api/routes/partner_auth.py)."""

    __tablename__ = "partner"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gewerk: Mapped[str | None] = mapped_column(Text)
    # Liste von AnsprechpartnerEintrag (siehe app/schemas/kontakt.py) --
    # exakt dasselbe Muster wie Kunde.ansprechpartner, mehrere Kontakte mit
    # Kategorisierung (operativ/Eskalationsstufe) statt eines einzelnen
    # Namens.
    ansprechpartner: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    telefon: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    adresse: Mapped[dict | None] = mapped_column(JSONB)
    notiz: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
