import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """Papierkorb: geloescht_am/geloescht_von statt eines echten DELETE (siehe
    app/services/papierkorb_service.py). geloescht_am IS NULL heisst aktiv --
    jede bestehende Liste/GET-Route muss das explizit filtern, RLS kennt
    dieses Konzept nicht. Kaskadierendes Loeschen/Wiederherstellen sowie das
    endgueltige (harte) Loeschen laufen ausschliesslich ueber den Service,
    nie direkt per session.delete()."""

    # Explizit timezone=True: anders als created_at/updated_at (die nur ueber
    # server_default=func.now() gesetzt werden) wird dieses Feld direkt aus
    # Python mit einem tz-aware datetime.now(UTC) befuellt (siehe
    # app/services/papierkorb_service.py) -- ohne den expliziten Typ bindet
    # asyncpg als TIMESTAMP WITHOUT TIME ZONE und die Query schlaegt fehl.
    geloescht_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    geloescht_von: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
