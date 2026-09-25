import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Modul-Katalog fuers Super-Admin-Menue (siehe Mandant.deaktivierte_module).
# "vorgaenge" (Auftrag anlegen/Chat/Foto/Status/Unterschrift/Zeit start-stopp,
# plus Kunde per Dropdown waehlen oder inline anlegen) ist bewusst NICHT Teil
# dieser Liste -- das ist der nicht abschaltbare Boden, ohne den "Auftraege
# tracken" ueberhaupt nicht ginge (ein Vorgang braucht zwingend einen Kunden).
# "zeiterfassung" und "statistik" waren frueher ein einziges Modul (siehe
# docs/BACKLOG.md) und sind rein informativ getrennt: "zeiterfassung" blendet
# die eigene Zeiterfassungs-Uebersicht (Profil-Kachel, /statistik-Formular +
# Wochenliste, Team-Zeiten) im Frontend aus, "statistik" die Auswertung/den
# Export (Kennzahlen-Kacheln, CSV/PDF) -- der Start/Stopp-Timer direkt am
# Vorgang gehoert weiterhin zum "vorgaenge"-Boden oben und bleibt in jedem
# Fall aktiv, backend-seitig gibt es dafuer daher keine neue Sperre.
# Muss mit der CHECK-Constraint ck_mandanten_fahrzeit_abrechnung_valid
# (Migration 0086) uebereinstimmen. Steuert die Fahrzeit/Fahrtkosten-
# Rechnungsvorschlaege (siehe rechnung_service.positionen_vorschlaege_fuer_vorgang).
MANDANT_FAHRZEIT_ABRECHNUNG = ("keine", "zeit", "km", "zeit_und_km")

MANDANT_MODULE = (
    "kundenverwaltung",
    "dispo",
    "material",
    "pruefzyklen",
    "abrechnung",
    "kundenportal",
    "dauerauftrag",
    "zeiterfassung",
    "statistik",
    "fahrzeuge",
    "highlights",
    "karten",
    "nachunternehmer",
    "postfach",
)


class Mandant(TimestampMixin, Base):
    __tablename__ = "mandanten"
    __table_args__ = (
        CheckConstraint(
            "status IN ('aktiv','pausiert','gekuendigt')", name="status_valid"
        ),
        CheckConstraint(
            "scheduler_stunde_utc IS NULL OR (scheduler_stunde_utc >= 0 AND scheduler_stunde_utc <= 23)",
            name="ck_mandanten_scheduler_stunde_utc_valid",
        ),
        CheckConstraint(
            "wiedervorlage_standard_tage IS NULL OR wiedervorlage_standard_tage > 0",
            name="ck_mandanten_wiedervorlage_standard_tage_valid",
        ),
        CheckConstraint(
            "km_satz_netto IS NULL OR km_satz_netto >= 0", name="ck_mandanten_km_satz_netto_nicht_negativ"
        ),
        CheckConstraint(
            f"fahrzeit_abrechnung IN {MANDANT_FAHRZEIT_ABRECHNUNG}",
            name="ck_mandanten_fahrzeit_abrechnung_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    branche: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="aktiv")
    branding: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Nacharbeit (Abschnitt 12/4.5): NULL = globaler Default aus Settings
    # (scheduler_default_stunde_utc). Erlaubt einem Mandanten, den taeglichen
    # Pruefzyklen-/Mahnwesen-Lauf auf eine fuer den eigenen Betrieb passende
    # Uhrzeit zu legen, statt fest fuer alle Mandanten auf 03:00 UTC.
    scheduler_stunde_utc: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # NULL = globaler Default (siehe WIEDERVORLAGE_STANDARD_TAGE in
    # app/services/scheduler_service.py) fuer die Wiedervorlage-Frist bei
    # status="wartet_kunde" (Vorgang.wiedervorlage_am) -- analog zu
    # scheduler_stunde_utc oben.
    wiedervorlage_standard_tage: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    # Opt-out: leer = alles an. Siehe MANDANT_MODULE fuer die gueltigen Werte.
    # Ausnahme "karten": anders als alle anderen Module bewusst opt-IN
    # (Default-Liste enthaelt "karten"), weil eine aktivierte Kartenansicht
    # laufende Mapbox-Kosten verursacht -- siehe Migration 0048, die
    # bestehende Mandanten auf denselben Stand bringt.
    deaktivierte_module: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["karten"]
    )
    # Firmenstammdaten fuer den PDF-Briefkopf (Angebot): adresse (dict mit
    # strasse/plz/ort, gleiche Form wie Kunde.adresse), telefon, email,
    # website, bank_name, iban, bic, handelsregister, geschaeftsfuehrung,
    # ust_idnr. Bewusst als loses JSONB statt einzelner Spalten, analog zu
    # Kunde.adresse -- spart eine Migration pro zusaetzlichem Feld.
    firmendaten: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    logo_object_key: Mapped[str | None] = mapped_column(Text)
    # Vorbelegung fuer neu angelegte Leistungsverzeichnis-Positionen im Modus
    # "berechnet" (siehe LeistungsverzeichnisPosition) -- wirkt NUR beim
    # Anlegen, spaeter geaenderte Mandant-Defaults rechnen bereits
    # bestehende Positionen bewusst nicht rueckwirkend neu.
    standard_lohn_gemeinkosten_prozent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    standard_gewinn_wagnis_prozent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    # Fahrzeit-Abrechnung (Stufe 4, docs/konzepte/ZEITERFASSUNG.md Abschnitt
    # 5.3/8) -- beide NULL/'keine' aendert am bisherigen Verhalten nichts.
    km_satz_netto: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    fahrzeit_abrechnung: Mapped[str] = mapped_column(Text, nullable=False, default="keine")
