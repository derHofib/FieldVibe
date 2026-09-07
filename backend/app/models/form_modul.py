"""ORM-Modelle fuer Formular-Modul v2 (siehe Migration 0076/0077 sowie
docs/phases fuer den Migrationsplan). Trennt Datenerfassung (FormSchema/
FormGroup/FormField) von Visualisierung (FormView/FormViewFieldLayout/
FormPresentationElement) und regelbasierter Logik (FormLogicRule).

Referenzen zwischen diesen Tabellen laufen ueber form_fields.key/
form_groups.key (stabile Strings je schema_id), NICHT ueber die UUID-
Primaerschluessel -- siehe Docstring der Migration 0076 fuer die
Begruendung. Die alten Tabellen (app/models/formular.py) bleiben bis
Schritt 10 des Migrationsplans parallel in Betrieb.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SCHEMA_STATUS = ("draft", "published", "archived")
VIEW_TYPEN = ("capture", "print", "summary", "table", "public")
PRAESENTATIONS_TYPEN = ("heading", "richtext", "divider", "spacer", "callout", "image", "computed_text")
LOGIC_EFFEKTE = ("show", "hide", "require", "readonly", "set_value")
SUBMISSION_STATUS = ("offen", "abgeschlossen")

FELD_TYPEN = (
    "text",
    "textarea",
    "zahl",
    "datum",
    "dropdown",
    "mehrfachauswahl",
    "ja_nein",
    "bewertung",
    "foto",
    "unterschrift",
    "gps",
    "qr_scan",
)
FELD_TYPEN_MIT_DATENQUELLE = ("text", "textarea", "zahl", "datum")
DATENQUELLEN = (
    "vorgang.vorgangsnummer",
    "vorgang.titel",
    "vorgang.beschreibung",
    "vorgang.leistungstyp",
    "vorgang.faelligkeit_am",
    "vorgang.adresse",
    "vorgang.zugewiesener_name",
    "kunde.kundennummer",
    "kunde.name",
    "kunde.adresse",
    "kunde.ansprechpartner",
    "anlage.bezeichnung",
    "anlage.adresse",
    "anlage.hersteller",
    "anlage.modell",
    "anlage.seriennummer",
    "anlage.anlagentyp",
    "standort.bezeichnung",
    "standort.adresse",
)
LEISTUNGSTYPEN = ("installation", "pruefung", "wartung", "stoerung", "beratung", "planung")


class FormSchema(Base, TimestampMixin):
    __tablename__ = "form_schemas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    vorgaenger_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id"), nullable=True
    )
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class FormGroup(Base):
    __tablename__ = "form_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    repeatable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    min_items: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    max_items: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class FormField(Base):
    __tablename__ = "form_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["schema_id", "group_key"],
            ["form_groups.schema_id", "form_groups.key"],
            name="fk_form_fields_group_key_form_groups",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    feld_typ: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    hilfetext: Mapped[str | None] = mapped_column(Text, nullable=True)
    pflichtfeld: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    default_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    optionen: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    group_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    datenquelle: Mapped[str | None] = mapped_column(Text, nullable=True)
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class FormView(Base, TimestampMixin):
    __tablename__ = "form_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    konfiguration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    erstellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class FormViewFieldLayout(Base):
    __tablename__ = "form_view_field_layouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_views.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    seite: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    x_mm: Mapped[float] = mapped_column(nullable=False, server_default="0")
    y_mm: Mapped[float] = mapped_column(nullable=False, server_default="0")
    breite_mm: Mapped[float] = mapped_column(nullable=False, server_default="85")
    hoehe_mm: Mapped[float] = mapped_column(nullable=False, server_default="8")


class FormPresentationElement(Base):
    __tablename__ = "form_presentation_elements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_views.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    inhalt: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    seite: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    x_mm: Mapped[float | None] = mapped_column(nullable=True)
    y_mm: Mapped[float | None] = mapped_column(nullable=True)
    breite_mm: Mapped[float | None] = mapped_column(nullable=True)
    hoehe_mm: Mapped[float | None] = mapped_column(nullable=True)


class FormLogicRule(Base):
    __tablename__ = "form_logic_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False
    )
    view_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_views.id", ondelete="CASCADE"), nullable=True
    )
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    effect: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    reihenfolge: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class FormAuftragstypZuordnung(Base):
    __tablename__ = "form_auftragstyp_zuordnungen"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    schema_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False
    )
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    pflicht_vor_abschluss: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class FormSubmission(Base, TimestampMixin):
    __tablename__ = "form_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    vorgang_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vorgaenge.id", ondelete="CASCADE"), nullable=False
    )
    schema_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("form_schemas.id"), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="offen")
    ausgefuellt_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    kundensichtbar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Explizit timezone=True: aus Python mit datetime.now(timezone.utc)
    # befuellt, nicht ueber server_default -- siehe SoftDeleteMixin-
    # Docstring in app/db/base.py fuer dieselbe Falle.
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FormSubmissionAudit(Base):
    __tablename__ = "form_submission_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    mandant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    alter_wert: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    neuer_wert: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    geaendert_von: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    geaendert_am: Mapped[datetime] = mapped_column(server_default="now()", nullable=False)
