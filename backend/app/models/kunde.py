import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

KUNDE_TYPEN = ("privat", "gewerbe", "oeffentlich", "hausverwaltung")
# Hausverwaltungen verwalten fremdes Eigentum beruflich und rechnen ueber den Verwalter ab;
# sie zaehlen deshalb wie Gewerbe und Behoerden als Unternehmer-Kunden.
KUNDE_TYPEN_GEWERBLICH = ("gewerbe", "oeffentlich", "hausverwaltung")
# Muss mit der CHECK-Constraint aus Migration 0109 uebereinstimmen.
KUNDE_E_RECHNUNG_FORMATE = ("zugferd", "xrechnung")


class Kunde(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "kunden"
    __table_args__ = (
        UniqueConstraint("mandant_id", "kundennummer", name="uq_kunden_mandant_kundennummer"),
        CheckConstraint(f"typ IS NULL OR typ IN {KUNDE_TYPEN}", name="ck_kunden_typ_valid"),
        CheckConstraint(
            f"e_rechnung_format IS NULL OR e_rechnung_format IN {KUNDE_E_RECHNUNG_FORMATE}",
            name="ck_kunden_e_rechnung_format_valid",
        ),
        CheckConstraint(
            "debitorenkonto IS NULL OR debitorenkonto ~ '^[0-9]{5,9}$'", name="ck_kunden_debitorenkonto_format"
        ),
        # Teil-Index: nicht vergebene Konten (NULL) duerfen beliebig oft vorkommen.
        Index(
            "uq_kunden_mandant_debitorenkonto",
            "mandant_id",
            "debitorenkonto",
            unique=True,
            postgresql_where=text("debitorenkonto IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kundennummer: Mapped[str] = mapped_column(Text, nullable=False)
    # DATEV-Personenkonto (Sachkontenlaenge + 1 Stellen). Wird beim ersten
    # DATEV-Export lazy vergeben (datev_service) und bleibt danach stabil;
    # manuell setzbar. Auch Papierkorb-Kunden behalten ihr Konto: alte Belege
    # verweisen darauf, die Nummer darf nie an einen anderen Kunden gehen.
    debitorenkonto: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    typ: Mapped[str | None] = mapped_column(Text)
    ansprechpartner: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    adresse: Mapped[dict | None] = mapped_column(JSONB)
    notiz: Mapped[str | None] = mapped_column(Text)
    # Umsatzsteuer-Identifikationsnummer -- Pflichtangabe (EN16931 BT-48) in
    # einer ZUGFeRD-Rechnung an gewerbliche/oeffentliche Kunden, siehe
    # e_invoice_service.pruefe_en16931_vollstaendigkeit(). Bei privaten
    # Kunden schlicht nicht vorhanden, daher nullable statt Pflichtfeld.
    ust_idnr: Mapped[str | None] = mapped_column(Text)
    # Routing-Kennung oeffentlicher Auftraggeber (BT-10 der XRechnung), geprueft
    # in app/services/leitweg_id.py.
    leitweg_id: Mapped[str | None] = mapped_column(Text)
    # Profilwahl der E-Rechnung; NULL = Automatik (Leitweg-ID -> xrechnung, sonst
    # zugferd), siehe e_invoice_service.profil_fuer.
    e_rechnung_format: Mapped[str | None] = mapped_column(Text)
    # Ablauf der Bescheinigung USt 1 TG (§ 13b Abs. 2 Nr. 4 UStG): Voraussetzung
    # fuer Reverse-Charge-Positionen (Steuerkategorie AE) an diesen Kunden.
    ust_13b_nachweis_bis: Mapped[date | None] = mapped_column(Date)
    # Personalisierter Kundenportal-Login-Link (/portal/l/{portal_slug}): ein
    # Link pro Kunde, nicht pro Ansprechpartner -- jeder Mitarbeiter des
    # Kunden mit einem eigenen KundenportalZugang meldet sich darueber mit
    # seiner eigenen E-Mail/seinem eigenen Passwort an (siehe
    # app/api/routes/kundenportal_auth.py). Ersetzt nie die Passwort-Eingabe.
    portal_slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # S3-Objekt-Key eines vom mandant_admin hochgeladenen Firmenlogos, das
    # auf der (fuer den Kunden personalisierten) Portal-Login-Seite gezeigt
    # wird. NULL = kein Logo hinterlegt.
    logo_object_key: Mapped[str | None] = mapped_column(Text)

    @property
    def ist_gewerblich(self) -> bool:
        """Einziges Kriterium fuer "B2B" (E-Rechnung-Modus b2b) und "kein Privatkunde"
        (Hinweise nach § 14 Abs. 4 Nr. 9 UStG): ein gewerblicher Typ, eine USt-IdNr. oder
        eine Leitweg-ID. Kunden ohne Typ und ohne diese Angaben gelten als Privatkunden."""
        return bool(
            self.typ in KUNDE_TYPEN_GEWERBLICH or (self.ust_idnr or "").strip() or (self.leitweg_id or "").strip()
        )
