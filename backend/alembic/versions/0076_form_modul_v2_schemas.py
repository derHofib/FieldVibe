"""Formular-Modul v2: Trennung von Datenerfassung (FormSchema/FormField/
FormGroup) und Visualisierung (FormView/FormPresentationElement/
FormViewFieldLayout), plus regelbasierte Logik (FormLogicRule) und
Audit-Trail fuer Ausfuellungen (FormSubmissionAudit).

Rein additiv -- die bestehenden Tabellen (formulare, formularfelder,
formular_auftragstyp_zuordnungen, vorgang_formulare) bleiben unveraendert
bestehen und werden vom Backend vorerst weiter bedient. Der Backfill in
diese neuen Tabellen ist eine eigene, spaetere Migration (siehe
docs/phases o.ae. fuer den Migrationsplan), damit Schema-Aenderung und
Daten-Uebernahme unabhaengig voneinander getestet/zurueckgerollt werden
koennen.

Schluessel-Entscheidung: form_fields.key (stabiler String je schema_id,
NICHT die UUID) ist die Referenz, die Regeln/Bindings/Views verwenden --
UUIDs bleiben nur Primaerschluessel fuer FKs innerhalb dieser Migration.
Das ist der Hauptunterschied zum alten Modell (formularfelder.id als
Snapshot-Schluessel), noetig damit Formular-Kopien/Versionen ihre
Feld-Referenzen behalten.

Revision ID: 0076
Revises: 0075
Create Date: 2026-09-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0076"
down_revision: Union[str, None] = "0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Bewusst OHNE "abschnitt" gegenueber dem alten FORMULARFELD_TYPEN (siehe
# app/models/formular.py) -- reine Gliederungs-Ueberschriften ohne
# Antwortwert sind im neuen Modell FormPresentationElement(type=heading),
# kein FormField mehr (siehe Docstring oben, Migrationsplan-Punkt 2).
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
SCHEMA_STATUS = ("draft", "published", "archived")
VIEW_TYPEN = ("capture", "print", "summary", "table", "public")
PRAESENTATIONS_TYPEN = ("heading", "richtext", "divider", "spacer", "callout", "image", "computed_text")
LOGIC_EFFEKTE = ("show", "hide", "require", "readonly", "set_value")
SUBMISSION_STATUS = ("offen", "abgeschlossen")
LEISTUNGSTYPEN = ("installation", "pruefung", "wartung", "stoerung", "beratung", "planung")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """
    )


def upgrade() -> None:
    # --- form_schemas ----------------------------------------------------
    op.create_table(
        "form_schemas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        # Zeigt auf die vorherige Version derselben logischen Vorlage --
        # NULL bei Version 1. Bildet die Versionskette, die den alten
        # formular_snapshot ersetzt (siehe Migrationsplan): eine
        # form_submission haelt nur schema_id + schema_version, alte
        # Versionen bleiben (status=archived) unveraendert in der DB
        # stehen statt in einem JSONB-Snapshot dupliziert zu werden.
        sa.Column("vorgaenger_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_schemas_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_form_schemas_erstellt_von_users"),
        sa.ForeignKeyConstraint(
            ["vorgaenger_id"], ["form_schemas.id"], name="fk_form_schemas_vorgaenger_id_form_schemas"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_form_schemas_updated_at BEFORE UPDATE ON form_schemas "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_form_schemas_mandant_id", "form_schemas", ["mandant_id"])
    op.create_index("ix_form_schemas_vorgaenger_id", "form_schemas", ["vorgaenger_id"])
    # create_check_constraint statt CheckConstraint(name=...) im create_table:
    # der naming_convention-Eintrag "ck": "ck_%(table_name)s_%(constraint_name)s"
    # (app/db/base.py) wuerde einen bereits vollstaendigen Namen sonst doppelt
    # praefigieren (siehe z.B. das historisch so entstandene
    # ck_formularfelder_ck_formularfelder_feld_typ_valid in Migration 0052) --
    # create_check_constraint nimmt nur das Suffix und wendet die Konvention
    # korrekt einmal an.
    op.create_check_constraint("status_valid", "form_schemas", f"status IN {SCHEMA_STATUS}")
    op.create_check_constraint("version_valid", "form_schemas", "version >= 1")
    _enable_rls("form_schemas")

    # --- form_groups -------------------------------------------------------
    op.create_table(
        "form_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("repeatable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_items", sa.SmallInteger(), nullable=True),
        sa.Column("max_items", sa.SmallInteger(), nullable=True),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_groups_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["form_schemas.id"], name="fk_form_groups_schema_id_form_schemas", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("schema_id", "key", name="uq_form_groups_schema_id_key"),
    )
    op.create_index("ix_form_groups_mandant_id", "form_groups", ["mandant_id"])
    op.create_index("ix_form_groups_schema_id", "form_groups", ["schema_id"])
    op.create_check_constraint("min_items_valid", "form_groups", "min_items IS NULL OR min_items >= 0")
    op.create_check_constraint(
        "max_items_valid",
        "form_groups",
        "max_items IS NULL OR min_items IS NULL OR max_items >= min_items",
    )
    _enable_rls("form_groups")

    # --- form_fields -------------------------------------------------------
    op.create_table(
        "form_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("feld_typ", sa.Text(), nullable=False),
        sa.Column("label", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hilfetext", sa.Text(), nullable=True),
        sa.Column("pflichtfeld", sa.Boolean(), nullable=False, server_default=sa.false()),
        # min/max/regex/einheit/thresholds je feld_typ -- Pendant zum alten
        # "optionen", aber fachlich auf Validierung/Grenzwerte beschraenkt;
        # Auswahlwerte (dropdown/mehrfachauswahl) und Skala (bewertung)
        # bleiben in optionen, siehe dort.
        sa.Column("validation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("default_value", postgresql.JSONB(), nullable=True),
        sa.Column("optionen", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        # Verweist auf form_groups.key derselben schema_id (siehe Composite-FK
        # unten) -- NULL = Feld liegt direkt im Root, nicht in einer
        # Wiederholgruppe. Es gibt bewusst KEIN parentGroupKey auf
        # form_groups selbst (siehe Migration form_groups) -- maximal eine
        # Verschachtelungsebene.
        sa.Column("group_key", sa.Text(), nullable=True),
        sa.Column("datenquelle", sa.Text(), nullable=True),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_fields_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["form_schemas.id"], name="fk_form_fields_schema_id_form_schemas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["schema_id", "group_key"],
            ["form_groups.schema_id", "form_groups.key"],
            name="fk_form_fields_group_key_form_groups",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("schema_id", "key", name="uq_form_fields_schema_id_key"),
    )
    op.create_index("ix_form_fields_mandant_id", "form_fields", ["mandant_id"])
    op.create_index("ix_form_fields_schema_id", "form_fields", ["schema_id"])
    op.create_index("ix_form_fields_schema_id_group_key", "form_fields", ["schema_id", "group_key"])
    op.create_check_constraint("feld_typ_valid", "form_fields", f"feld_typ IN {FELD_TYPEN}")
    op.create_check_constraint(
        "datenquelle_valid", "form_fields", f"datenquelle IS NULL OR datenquelle IN {DATENQUELLEN}"
    )
    _enable_rls("form_fields")

    # --- form_views ----------------------------------------------------------
    op.create_table(
        "form_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # Layout: Sections/Steps/Spalten-Zuordnung, Reihenfolge -- Struktur
        # ist je type unterschiedlich, deshalb bewusst freies JSONB statt
        # eigener Tabellen je Layout-Art (analog zu Formularfeld.optionen).
        sa.Column("konfiguration", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_views_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["form_schemas.id"], name="fk_form_views_schema_id_form_schemas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_form_views_erstellt_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_form_views_updated_at BEFORE UPDATE ON form_views "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_form_views_mandant_id", "form_views", ["mandant_id"])
    op.create_index("ix_form_views_schema_id", "form_views", ["schema_id"])
    op.create_check_constraint("type_valid", "form_views", f"type IN {VIEW_TYPEN}")
    _enable_rls("form_views")

    # --- form_view_field_layouts --------------------------------------------
    op.create_table(
        "form_view_field_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Referenziert form_fields.key -- NICHT als DB-FK erzwungen (view_id
        # allein trägt hier keine schema_id-Spalte, ein sauberer Composite-FK
        # würde eine denormalisierte schema_id auf dieser Tabelle
        # erzwingen). Analog zur bestehenden Konvention in
        # app/models/formular.py (Formularfeld.seite < formular.anzahl_seiten
        # ist ebenfalls nur anwendungsseitig geprueft): wird in
        # app/api/routes/form_views.py beim Schreiben gegen die form_fields
        # der zugehoerigen schema_id validiert.
        sa.Column("field_key", sa.Text(), nullable=False),
        sa.Column("seite", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("x_mm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("y_mm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("breite_mm", sa.Float(), nullable=False, server_default="85"),
        sa.Column("hoehe_mm", sa.Float(), nullable=False, server_default="8"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_form_view_field_layouts_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["view_id"], ["form_views.id"], name="fk_form_view_field_layouts_view_id_form_views", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("view_id", "field_key", name="uq_form_view_field_layouts_view_id_field_key"),
    )
    op.create_index("ix_form_view_field_layouts_mandant_id", "form_view_field_layouts", ["mandant_id"])
    op.create_index("ix_form_view_field_layouts_view_id", "form_view_field_layouts", ["view_id"])
    op.create_check_constraint("seite_valid", "form_view_field_layouts", "seite >= 0")
    op.create_check_constraint("x_mm_valid", "form_view_field_layouts", "x_mm >= 0")
    op.create_check_constraint("y_mm_valid", "form_view_field_layouts", "y_mm >= 0")
    op.create_check_constraint("breite_mm_valid", "form_view_field_layouts", "breite_mm > 0")
    op.create_check_constraint("hoehe_mm_valid", "form_view_field_layouts", "hoehe_mm > 0")
    _enable_rls("form_view_field_layouts")

    # --- form_presentation_elements -----------------------------------------
    op.create_table(
        "form_presentation_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        # Bei heading/richtext/callout: {"text": {"de": "..."}}. Bei
        # computed_text: {"template": "Anlage {{anlage.name}} geprueft am
        # {{datum}}"} -- Platzhalter werden dieselben Datenquellen/Werte wie
        # FormField.datenquelle bzw. Submission-Werte referenzieren. Bei
        # image: {"asset_key": "..."}."
        sa.Column("inhalt", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        # Freie Positionierung nur fuer print-Views relevant (sonst NULL/0
        # und reihenfolge entscheidet) -- gleiches Prinzip wie
        # form_view_field_layouts, deshalb dieselben Spalten statt einer
        # eigenen Layout-Tabelle nur fuer Praesentationselemente.
        sa.Column("seite", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("x_mm", sa.Float(), nullable=True),
        sa.Column("y_mm", sa.Float(), nullable=True),
        sa.Column("breite_mm", sa.Float(), nullable=True),
        sa.Column("hoehe_mm", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_form_presentation_elements_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["view_id"],
            ["form_views.id"],
            name="fk_form_presentation_elements_view_id_form_views",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_form_presentation_elements_mandant_id", "form_presentation_elements", ["mandant_id"])
    op.create_index("ix_form_presentation_elements_view_id", "form_presentation_elements", ["view_id"])
    op.create_check_constraint(
        "type_valid", "form_presentation_elements", f"type IN {PRAESENTATIONS_TYPEN}"
    )
    _enable_rls("form_presentation_elements")

    # --- form_logic_rules ----------------------------------------------------
    op.create_table(
        "form_logic_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NULL = gilt global fuer alle Views dieses Schemas; gesetzt = nur in
        # dieser einen View wirksam (z.B. ein Feld nur in der Kunden-
        # Print-Ansicht ausblenden, in der internen Capture-View aber
        # zeigen). Siehe Migrationsplan/Antwort zu mehreren Protokoll-Views.
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Ziel der Regel: ein FormField.key oder FormGroup.key (fuer
        # "ganzen Abschnitt/Gruppe ausblenden") -- welches von beidem, ergibt
        # sich aus dem Kontext (Anwendungslogik prueft beim Speichern, dass
        # der key in schema_id tatsaechlich existiert).
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        # JSONLogic-Ausdruck, siehe shared Logik-Engine (Python-Package
        # app/services/form_logic_engine.py + TS-Pendant im Frontend, ueber
        # gemeinsame Test-Fixtures synchron gehalten statt gemeinsamen Code,
        # da Backend Python und Frontend TypeScript ist).
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        # Nur fuer effect='set_value' relevant.
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("reihenfolge", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_logic_rules_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["form_schemas.id"], name="fk_form_logic_rules_schema_id_form_schemas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["view_id"], ["form_views.id"], name="fk_form_logic_rules_view_id_form_views", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_form_logic_rules_mandant_id", "form_logic_rules", ["mandant_id"])
    op.create_index("ix_form_logic_rules_schema_id", "form_logic_rules", ["schema_id"])
    op.create_index("ix_form_logic_rules_view_id", "form_logic_rules", ["view_id"])
    op.create_check_constraint("effect_valid", "form_logic_rules", f"effect IN {LOGIC_EFFEKTE}")
    op.create_check_constraint(
        "set_value_hat_value", "form_logic_rules", "effect != 'set_value' OR value IS NOT NULL"
    )
    _enable_rls("form_logic_rules")

    # --- form_auftragstyp_zuordnungen ---------------------------------------
    op.create_table(
        "form_auftragstyp_zuordnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leistungstyp", sa.Text(), nullable=False),
        sa.Column("pflicht_vor_abschluss", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_form_auftragstyp_zuordnungen_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"],
            ["form_schemas.id"],
            name="fk_form_auftragstyp_zuordnungen_schema_id_form_schemas",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "schema_id", "leistungstyp", name="uq_form_auftragstyp_zuordnungen_schema_id_leistungstyp"
        ),
    )
    op.create_index("ix_form_auftragstyp_zuordnungen_mandant_id", "form_auftragstyp_zuordnungen", ["mandant_id"])
    op.create_index("ix_form_auftragstyp_zuordnungen_schema_id", "form_auftragstyp_zuordnungen", ["schema_id"])
    op.create_check_constraint(
        "leistungstyp_valid", "form_auftragstyp_zuordnungen", f"leistungstyp IN {LEISTUNGSTYPEN}"
    )
    _enable_rls("form_auftragstyp_zuordnungen")

    # --- form_submissions ----------------------------------------------------
    op.create_table(
        "form_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Eingefroren beim Start der Ausfuellung -- ersetzt den alten
        # formular_snapshot: statt die Felddefinitionen zu duplizieren,
        # bleibt einfach die referenzierte form_schemas-Zeile in ihrer
        # damaligen Version unveraendert (status wechselt hoechstens auf
        # 'archived', wird nie geloescht/ueberschrieben), siehe Docstring
        # oben.
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        # {key: wert} fuer Root-Felder, {group_key: [{...}, {...}]} fuer
        # Wiederholgruppen-Zeilen.
        sa.Column("values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("ausgefuellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kundensichtbar", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("abgeschlossen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_form_submissions_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["vorgang_id"], ["vorgaenge.id"], name="fk_form_submissions_vorgang_id_vorgaenge", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["form_schemas.id"], name="fk_form_submissions_schema_id_form_schemas"
        ),
        sa.ForeignKeyConstraint(
            ["ausgefuellt_von"], ["users.id"], name="fk_form_submissions_ausgefuellt_von_users"
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_form_submissions_updated_at BEFORE UPDATE ON form_submissions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_form_submissions_mandant_id", "form_submissions", ["mandant_id"])
    op.create_index("ix_form_submissions_vorgang_id", "form_submissions", ["vorgang_id"])
    op.create_index("ix_form_submissions_schema_id", "form_submissions", ["schema_id"])
    op.create_check_constraint("status_valid", "form_submissions", f"status IN {SUBMISSION_STATUS}")
    _enable_rls("form_submissions")

    # --- form_submission_audit ----------------------------------------------
    op.create_table(
        "form_submission_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_key", sa.Text(), nullable=False),
        sa.Column("alter_wert", postgresql.JSONB(), nullable=True),
        sa.Column("neuer_wert", postgresql.JSONB(), nullable=True),
        sa.Column("geaendert_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geaendert_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_form_submission_audit_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["form_submissions.id"],
            name="fk_form_submission_audit_submission_id_form_submissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["geaendert_von"], ["users.id"], name="fk_form_submission_audit_geaendert_von_users"
        ),
    )
    op.create_index("ix_form_submission_audit_mandant_id", "form_submission_audit", ["mandant_id"])
    op.create_index("ix_form_submission_audit_submission_id", "form_submission_audit", ["submission_id"])
    _enable_rls("form_submission_audit")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_submission_audit")
    op.drop_table("form_submission_audit")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_submissions")
    op.drop_table("form_submissions")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_auftragstyp_zuordnungen")
    op.drop_table("form_auftragstyp_zuordnungen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_logic_rules")
    op.drop_table("form_logic_rules")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_presentation_elements")
    op.drop_table("form_presentation_elements")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_view_field_layouts")
    op.drop_table("form_view_field_layouts")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_views")
    op.drop_table("form_views")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_fields")
    op.drop_table("form_fields")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_groups")
    op.drop_table("form_groups")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON form_schemas")
    op.drop_table("form_schemas")
