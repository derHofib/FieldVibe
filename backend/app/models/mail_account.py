import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MAIL_ACCOUNT_VERSCHLUESSELUNG = ("ssl", "starttls", "keine")


class MailAccount(TimestampMixin, Base):
    """Persoenliches IMAP/SMTP-Postfach eines Nutzers -- Gegenstueck zu
    MandantIntegration (mandantenweit), aber je Nutzer, damit FieldVibe
    Outlook & Co. ersetzen kann, ohne dass Kollegen sich gegenseitig in die
    Mails schauen. RLS beschraenkt nur auf den Mandanten; die Einschraenkung
    auf den eigenen Nutzer passiert app-seitig (gleiches Muster wie
    GespeicherterFilter), weil Postgres-RLS keinen Zugriff auf den
    JWT-User hat, ohne ihn zusaetzlich per current_setting zu uebergeben --
    fuer ein Einzelnutzer-Postfach ohne Team-Freigabe unnoetiger Aufwand."""

    __tablename__ = "mail_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "email_adresse", name="uq_mail_accounts_user_email"),
        CheckConstraint(
            f"imap_verschluesselung IN {MAIL_ACCOUNT_VERSCHLUESSELUNG}",
            name="ck_mail_accounts_imap_verschluesselung_valid",
        ),
        CheckConstraint(
            f"smtp_verschluesselung IN {MAIL_ACCOUNT_VERSCHLUESSELUNG}",
            name="ck_mail_accounts_smtp_verschluesselung_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    email_adresse: Mapped[str] = mapped_column(Text, nullable=False)

    imap_host: Mapped[str] = mapped_column(Text, nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_verschluesselung: Mapped[str] = mapped_column(Text, nullable=False, default="ssl")
    imap_benutzername: Mapped[str] = mapped_column(Text, nullable=False)

    smtp_host: Mapped[str] = mapped_column(Text, nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_verschluesselung: Mapped[str] = mapped_column(Text, nullable=False, default="starttls")
    smtp_benutzername: Mapped[str] = mapped_column(Text, nullable=False)

    # Ein Fernet-verschluesseltes Passwort fuer beide Protokolle -- die
    # allermeisten Provider (und alle Test-Postfaecher, die wir realistisch
    # anbinden) nutzen dasselbe Passwort fuer IMAP und SMTP. Getrennte Felder
    # waeren fuer den seltenen Sonderfall ein Formular mit doppelt so vielen
    # Passwortfeldern -- kann bei Bedarf spaeter ergaenzt werden.
    passwort_verschluesselt: Mapped[str] = mapped_column(Text, nullable=False)

    signatur: Mapped[str | None] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Sync-Fortschritt je Konto -- IMAP-UID-basiert, gleiches Prinzip wie
    # MandantIntegration.config["last_uid"] beim Rechnungseingang-Import,
    # hier aber pro Ordner noetig (jeder Ordner hat einen eigenen
    # UID-Zaehler), deshalb erst in Stufe 2 als eigene Tabelle statt hier.
    letzter_sync_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letzter_sync_fehler: Mapped[str | None] = mapped_column(Text)
