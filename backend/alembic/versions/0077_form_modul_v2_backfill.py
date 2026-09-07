"""Formular-Modul v2 Schritt 2: Backfill der bestehenden formulare/
formularfelder/formular_auftragstyp_zuordnungen/vorgang_formulare in die
neuen Tabellen aus Migration 0076.

Die alten Tabellen bleiben unveraendert bestehen und werden vom Backend
vorerst weiter bedient (siehe Docstring 0076) -- diese Migration fuegt
ausschliesslich neue Zeilen ein, aendert/loescht nichts an den alten.

Kern-Trick, der jede UUID<->key-Remapping-Tabelle erspart:
- form_schemas.id wird 1:1 von formulare.id uebernommen (statt einer neuen
  UUID). Es gibt keinen FK zwischen den beiden Tabellen, eine geteilte ID
  ist also unproblematisch und macht formular_id -> schema_id trivial.
- form_fields.key wird 1:1 der String der alten formularfelder.id. Damit
  ist vorgang_formulare.antworten (JSONB, keyed by der alten Feld-UUID als
  String) OHNE Remapping identisch als form_submissions.values uebernehmbar
  -- die Keys stimmen bereits ueberein.

feld_typ='abschnitt' hat im neuen Modell keine Entsprechung als FormField
(siehe FELD_TYPEN in 0076) -- solche Zeilen werden stattdessen als
FormPresentationElement(type='heading') in der neu erzeugten capture-View
angelegt.

Jede formulare-Zeile bekommt genau eine form_views-Zeile vom Typ 'capture',
deren form_view_field_layouts 1:1 aus den alten x_mm/y_mm/breite_mm/
hoehe_mm/seite-Spalten uebernommen werden -- das ist die "automatisch aus
den bestehenden Positionsdaten erzeugte capture-View" aus dem
Migrationsplan.

validation (min/max/regex/einheit) gibt es im alten Modell nicht als
eigenes Konzept -- bleibt bei Backfill leer ('{}'), kann spaeter ueber den
neuen Editor nachgetragen werden. optionen (Auswahlwerte/Skala) wird
unveraendert uebernommen, das Format ist identisch geblieben.

Revision ID: 0077
Revises: 0076
Create Date: 2026-09-07
"""
import json
import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0077"
down_revision: Union[str, None] = "0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    formulare = conn.execute(
        text(
            "SELECT id, mandant_id, name, beschreibung, aktiv, erstellt_von, "
            "created_at, updated_at FROM formulare"
        )
    ).mappings().all()

    for f in formulare:
        schema_id = f["id"]
        status = "published" if f["aktiv"] else "archived"
        conn.execute(
            text(
                "INSERT INTO form_schemas "
                "(id, mandant_id, name, beschreibung, version, status, erstellt_von, created_at, updated_at) "
                "VALUES (:id, :mandant_id, :name, :beschreibung, 1, :status, :erstellt_von, :created_at, :updated_at)"
            ),
            {
                "id": schema_id,
                "mandant_id": f["mandant_id"],
                "name": f["name"],
                "beschreibung": f["beschreibung"],
                "status": status,
                "erstellt_von": f["erstellt_von"],
                "created_at": f["created_at"],
                "updated_at": f["updated_at"],
            },
        )

        view_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO form_views "
                "(id, mandant_id, schema_id, type, name, konfiguration, erstellt_von, created_at, updated_at) "
                "VALUES (:id, :mandant_id, :schema_id, 'capture', 'Erfassung', '{}'::jsonb, "
                ":erstellt_von, :created_at, :updated_at)"
            ),
            {
                "id": view_id,
                "mandant_id": f["mandant_id"],
                "schema_id": schema_id,
                "erstellt_von": f["erstellt_von"],
                "created_at": f["created_at"],
                "updated_at": f["updated_at"],
            },
        )

        felder = conn.execute(
            text(
                "SELECT id, feld_typ, label, hilfetext, pflichtfeld, optionen, datenquelle, "
                "reihenfolge, seite, x_mm, y_mm, breite_mm, hoehe_mm "
                "FROM formularfelder WHERE formular_id = :fid ORDER BY reihenfolge"
            ),
            {"fid": schema_id},
        ).mappings().all()

        for feld in felder:
            if feld["feld_typ"] == "abschnitt":
                conn.execute(
                    text(
                        "INSERT INTO form_presentation_elements "
                        "(id, mandant_id, view_id, type, inhalt, reihenfolge, seite, x_mm, y_mm, breite_mm, hoehe_mm) "
                        "VALUES (gen_random_uuid(), :mandant_id, :view_id, 'heading', :inhalt, :reihenfolge, "
                        ":seite, :x_mm, :y_mm, :breite_mm, :hoehe_mm)"
                    ),
                    {
                        "mandant_id": f["mandant_id"],
                        "view_id": view_id,
                        "inhalt": json.dumps({"text": {"de": feld["label"]}}),
                        "reihenfolge": feld["reihenfolge"],
                        "seite": feld["seite"],
                        "x_mm": feld["x_mm"],
                        "y_mm": feld["y_mm"],
                        "breite_mm": feld["breite_mm"],
                        "hoehe_mm": feld["hoehe_mm"],
                    },
                )
                continue

            field_key = str(feld["id"])
            conn.execute(
                text(
                    "INSERT INTO form_fields "
                    "(id, mandant_id, schema_id, key, feld_typ, label, hilfetext, pflichtfeld, "
                    "validation, default_value, optionen, group_key, datenquelle, reihenfolge) "
                    "VALUES (gen_random_uuid(), :mandant_id, :schema_id, :key, :feld_typ, :label, "
                    ":hilfetext, :pflichtfeld, '{}'::jsonb, NULL, :optionen, NULL, :datenquelle, :reihenfolge)"
                ),
                {
                    "mandant_id": f["mandant_id"],
                    "schema_id": schema_id,
                    "key": field_key,
                    "feld_typ": feld["feld_typ"],
                    "label": json.dumps({"de": feld["label"]}),
                    "hilfetext": feld["hilfetext"],
                    "pflichtfeld": feld["pflichtfeld"],
                    "optionen": json.dumps(feld["optionen"]),
                    "datenquelle": feld["datenquelle"],
                    "reihenfolge": feld["reihenfolge"],
                },
            )
            conn.execute(
                text(
                    "INSERT INTO form_view_field_layouts "
                    "(id, mandant_id, view_id, field_key, seite, x_mm, y_mm, breite_mm, hoehe_mm) "
                    "VALUES (gen_random_uuid(), :mandant_id, :view_id, :field_key, :seite, :x_mm, :y_mm, "
                    ":breite_mm, :hoehe_mm)"
                ),
                {
                    "mandant_id": f["mandant_id"],
                    "view_id": view_id,
                    "field_key": field_key,
                    "seite": feld["seite"],
                    "x_mm": feld["x_mm"],
                    "y_mm": feld["y_mm"],
                    "breite_mm": feld["breite_mm"],
                    "hoehe_mm": feld["hoehe_mm"],
                },
            )

        zuordnungen = conn.execute(
            text(
                "SELECT leistungstyp, pflicht_vor_abschluss FROM formular_auftragstyp_zuordnungen "
                "WHERE formular_id = :fid"
            ),
            {"fid": schema_id},
        ).mappings().all()
        for z in zuordnungen:
            conn.execute(
                text(
                    "INSERT INTO form_auftragstyp_zuordnungen "
                    "(id, mandant_id, schema_id, leistungstyp, pflicht_vor_abschluss) "
                    "VALUES (gen_random_uuid(), :mandant_id, :schema_id, :leistungstyp, :pflicht)"
                ),
                {
                    "mandant_id": f["mandant_id"],
                    "schema_id": schema_id,
                    "leistungstyp": z["leistungstyp"],
                    "pflicht": z["pflicht_vor_abschluss"],
                },
            )

    submissions = conn.execute(
        text(
            "SELECT id, mandant_id, vorgang_id, formular_id, antworten, status, ausgefuellt_von, "
            "kundensichtbar, abgeschlossen_am, created_at, updated_at FROM vorgang_formulare"
        )
    ).mappings().all()
    for s in submissions:
        conn.execute(
            text(
                "INSERT INTO form_submissions "
                "(id, mandant_id, vorgang_id, schema_id, schema_version, values, status, "
                "ausgefuellt_von, kundensichtbar, abgeschlossen_am, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :mandant_id, :vorgang_id, :schema_id, 1, :values, :status, "
                ":ausgefuellt_von, :kundensichtbar, :abgeschlossen_am, :created_at, :updated_at)"
            ),
            {
                "mandant_id": s["mandant_id"],
                "vorgang_id": s["vorgang_id"],
                "schema_id": s["formular_id"],
                "values": json.dumps(s["antworten"]),
                "status": s["status"],
                "ausgefuellt_von": s["ausgefuellt_von"],
                "kundensichtbar": s["kundensichtbar"],
                "abgeschlossen_am": s["abgeschlossen_am"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
            },
        )


def downgrade() -> None:
    # Loescht nur die von dieser Migration eingefuegten Daten, keine der
    # Alt-Tabellen (formulare/formularfelder/vorgang_formulare bleiben
    # unberuehrt). Wie ueberall in diesem Projekt dient der Downgrade-Pfad
    # nur der lokalen Migrationszyklus-Pruefung (siehe z.B. 0075) -- zum
    # Zeitpunkt dieser Migration existieren noch keine ueber den neuen
    # Formular-Editor angelegten Zeilen in den Zieltabellen, ein simples
    # Leeren ist daher verlustfrei bezogen auf "echte" Daten.
    op.execute("DELETE FROM form_submissions")
    op.execute("DELETE FROM form_auftragstyp_zuordnungen")
    op.execute("DELETE FROM form_presentation_elements")
    op.execute("DELETE FROM form_view_field_layouts")
    op.execute("DELETE FROM form_views")
    op.execute("DELETE FROM form_fields")
    op.execute("DELETE FROM form_schemas")
