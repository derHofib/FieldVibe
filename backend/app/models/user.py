import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ROLES = (
    "super_admin",
    "mandant_admin",
    # Jeder mandant-eigene Nutzer, der KEINE der fest verdrahteten Rollen hat,
    # bekommt role='custom' und zeigt via account_typ_id auf einen vom
    # mandant_admin frei definierten Account-Typ (siehe app/models/account_typ.py)
    # -- die vormals fest verdrahteten Rollen disponent/techniker/controller/
    # mitarbeiter sind damit vollstaendig durch diesen Mechanismus abgeloest.
    "custom",
    # Papierkorb (siehe app/services/papierkorb_service.py): loesch_ansicht
    # sieht ausschliesslich den Papierkorb (rein lesend), loesch_operativ hat
    # zusaetzlich ueberall dieselben Rechte wie mandant_admin (siehe
    # app/api/deps.py:require_roles()) und darf zudem loeschen/
    # wiederherstellen/endgueltig loeschen. Beide Rollen sind nur durch
    # super_admin vergebbar (siehe app/api/routes/users.py), von
    # loesch_operativ darf es je Mandant hoechstens einen aktiven Account
    # geben (siehe Migration 0032, partial unique index). Bewusst AUSSERHALB
    # der mandant_admin-kontrollierten Account-Typen-Verwaltung, damit ein
    # Mandant-Admin nicht selbst steuern kann, wer seine geloeschten Daten
    # sieht/wiederherstellt.
    "loesch_ansicht",
    "loesch_operativ",
)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="role_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # Nur gesetzt, wenn role == 'custom' -- zeigt auf den vom mandant_admin
    # definierten Account-Typ, der die tatsaechlichen Rechte traegt.
    account_typ_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_typen.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Geordnete Liste von Seiten-Keys (siehe frontend/src/config/navSeiten.ts)
    # fuer die individualisierte, swipebare Bottom-Nav. NULL = Standardauswahl.
    bottom_nav_items: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
