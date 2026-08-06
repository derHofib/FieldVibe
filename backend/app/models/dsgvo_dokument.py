import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Plattformweite Compliance-Dokumente (nicht mandantengebunden) -- deckt den
# "P1"-Papierkram aus dem DSGVO-Fahrplan ab: fuer jeden Typ genau eine
# aktive Version, ein erneuter Upload ersetzt die vorherige.
DSGVO_DOKUMENT_TYPEN = (
    "avv_vorlage",
    "datenschutzerklaerung",
    "impressum",
    "loeschkonzept",
    "tom_dokument",
    "meldeprozess",
    "verzeichnis_verarbeitungstaetigkeiten",
)


class DsgvoDokument(Base):
    __tablename__ = "dsgvo_dokumente"
    __table_args__ = (
        CheckConstraint(f"typ IN {DSGVO_DOKUMENT_TYPEN}", name="ck_dsgvo_dokumente_typ_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Unique statt mandant-artiger Mehrfachbelegung: pro Typ genau ein
    # aktives Dokument, ein neuer Upload ersetzt (loescht) das alte Objekt.
    typ: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    dateiname: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    groesse_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hochgeladen_von: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
