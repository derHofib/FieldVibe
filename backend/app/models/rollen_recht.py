import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Nur die beiden frei konfigurierbaren Account-Typen -- super_admin,
# mandant_admin, disponent und techniker behalten ihr bisheriges, im Code
# fest verdrahtetes Rechte-Set (require_roles(...) an den jeweiligen Routen)
# unveraendert bei, damit ein Mandant sich durch eine Fehlkonfiguration nicht
# selbst aus der Verwaltung aussperren kann.
RECHTE_ROLLEN = ("controller", "mitarbeiter")
RECHTE_BEREICHE = (
    "vorgaenge",
    "kunden",
    "material",
    "dispo",
    "abrechnung",
    "statistik",
    "mitarbeiterverwaltung",
)
RECHTE_AKTIONEN = ("sehen", "bearbeiten")


class MandantRollenRecht(TimestampMixin, Base):
    """Pro Mandant konfigurierbare Sicht-/Bearbeiten-Rechte fuer die Account-
    Typen 'controller' und 'mitarbeiter'. Fehlt fuer eine (rolle, bereich,
    aktion)-Kombination eine Zeile, gilt der Code-Default aus
    app/services/rechte_service.py -- ein neu eingefuehrter Bereich ist so
    automatisch sinnvoll vorbelegt, ohne dass jeder Mandant ihn erst
    nachpflegen muesste."""

    __tablename__ = "mandant_rollen_rechte"
    __table_args__ = (
        UniqueConstraint(
            "mandant_id", "rolle", "bereich", "aktion", name="uq_mandant_rollen_rechte"
        ),
        CheckConstraint(f"rolle IN {RECHTE_ROLLEN}", name="ck_mandant_rollen_rechte_rolle_valid"),
        CheckConstraint(
            f"bereich IN {RECHTE_BEREICHE}", name="ck_mandant_rollen_rechte_bereich_valid"
        ),
        CheckConstraint(
            f"aktion IN {RECHTE_AKTIONEN}", name="ck_mandant_rollen_rechte_aktion_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    rolle: Mapped[str] = mapped_column(Text, nullable=False)
    bereich: Mapped[str] = mapped_column(Text, nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    erlaubt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
