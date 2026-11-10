"""Formular-Modul v2 Schritt 10: Alt-Tabellen entfernen.

Die alten Tabellen (formulare/formularfelder/formular_auftragstyp_
zuordnungen/vorgang_formulare, siehe Migration 0052) werden seit diesem
Release nicht mehr bedient -- die alten Backend-Routen (formulare.py,
vorgang_formulare.py), das alte Modell/Schema/Service sowie die alten
Frontend-Seiten wurden im selben Release entfernt. Es gibt also keinen
Zeitraum, in dem alte Routen nach dieser Migration noch neue Zeilen in die
Alt-Tabellen schreiben koennten -- der Backfill aus Migration 0077 ist
damit der letzte Stand, den es je geben wird.

Sicherheitscheck vor dem Drop: prueft per COUNT, dass jede Zeile in
formulare/vorgang_formulare tatsaechlich eine Entsprechung in
form_schemas/form_submissions hat (form_schemas.id = formulare.id, siehe
Docstring 0077; form_submissions ueber vorgang_id+schema_id+created_at,
da form_submissions.id in 0077 absichtlich NICHT deterministisch aus
vorgang_formulare.id uebernommen wurde). Bricht die Migration ab (statt
Daten kommentarlos zu verlieren), falls doch etwas fehlen sollte -- alembic
fuehrt jede Migration in einer Transaktion aus, ein Abbruch aendert also
nichts.

Revision ID: 0078
Revises: 0077
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0078"
down_revision: Union[str, None] = "0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_vollstaendig_migriert(conn) -> None:
    fehlende_schemas = conn.execute(
        text(
            "SELECT count(*) FROM formulare f "
            "WHERE NOT EXISTS (SELECT 1 FROM form_schemas s WHERE s.id = f.id)"
        )
    ).scalar_one()
    if fehlende_schemas:
        raise RuntimeError(
            f"{fehlende_schemas} formulare-Zeile(n) ohne Entsprechung in form_schemas -- "
            "Backfill (Migration 0077) unvollstaendig, Abbruch vor dem Drop der Alt-Tabellen."
        )

    fehlende_submissions = conn.execute(
        text(
            "SELECT count(*) FROM vorgang_formulare vf "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM form_submissions fs "
            "  WHERE fs.vorgang_id = vf.vorgang_id "
            "    AND fs.schema_id = vf.formular_id "
            "    AND fs.created_at = vf.created_at"
            ")"
        )
    ).scalar_one()
    if fehlende_submissions:
        raise RuntimeError(
            f"{fehlende_submissions} vorgang_formulare-Zeile(n) ohne Entsprechung in "
            "form_submissions -- Backfill (Migration 0077) unvollstaendig, Abbruch vor dem "
            "Drop der Alt-Tabellen."
        )


def upgrade() -> None:
    conn = op.get_bind()
    _assert_vollstaendig_migriert(conn)

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON vorgang_formulare")
    op.drop_table("vorgang_formulare")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formular_auftragstyp_zuordnungen")
    op.drop_table("formular_auftragstyp_zuordnungen")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formularfelder")
    op.drop_table("formularfelder")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON formulare")
    op.drop_table("formulare")


def downgrade() -> None:
    raise RuntimeError(
        "Kein Downgrade-Pfad: die Alt-Tabellen sind entfernt, ihre Struktur und Daten koennen "
        "aus den neuen Tabellen nicht mehr rekonstruiert werden (form_schemas.status kennt kein "
        "'aktiv', form_fields.key ist nicht mehr die alte UUID nach einer Bearbeitung ueber den "
        "neuen Editor, etc.). Ein Restore aus einem Datenbank-Backup vor dieser Migration ist der "
        "einzige Weg zurueck."
    )
