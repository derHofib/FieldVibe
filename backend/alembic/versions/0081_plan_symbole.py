"""Plan-Symbole: Mandanten-eigene Symbol-Bibliothek fuer den neuen Feldtyp
"foto_plan" (Foto mit einzeichenbaren Symbolen/Leitungswegen, z.B. Wallbox,
Leitungsschutzschalter, Zaehler -- siehe Nutzer-Anfrage). Eigene Tabelle
statt eines festen Code-Katalogs, weil der Symbol-Satz von Anfang an
mandantenspezifisch erweiterbar sein soll (eigene Hochladen/Benennen/
Loeschen-Verwaltung, siehe app/api/routes/plan_symbole.py).

Die Markierungen selbst (welches Symbol wo auf welchem Foto sitzt) leben
NICHT in einer eigenen Tabelle, sondern strukturiert im bestehenden
form_submissions.values-JSONB unter dem jeweiligen Feld-Key -- analog zum
bereits bestehenden Muster fuer "adresse"/"gps" (kein neues Datenmodell
noetig, siehe form_modul_service.py). form_fields.optionen.symbol_ids
(JSONB-Array von plan_symbole.id) legt je Feld fest, welche Symbole aus der
Mandanten-Bibliothek fuer *dieses* Feld ueberhaupt auswaehlbar sind.

Revision ID: 0081
Revises: 0080
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0081"
down_revision: Union[str, None] = "0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALTE_FELD_TYPEN = (
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
    "datei",
    "email",
    "telefon",
    "betrag",
    "adresse",
)
_NEUE_FELD_TYPEN = _ALTE_FELD_TYPEN + ("foto_plan",)


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
    op.create_table(
        "plan_symbole",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_plan_symbole_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_plan_symbole_erstellt_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_plan_symbole_updated_at BEFORE UPDATE ON plan_symbole "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_plan_symbole_mandant_id", "plan_symbole", ["mandant_id"])
    _enable_rls("plan_symbole")

    op.drop_constraint("feld_typ_valid", "form_fields", type_="check")
    op.create_check_constraint("feld_typ_valid", "form_fields", f"feld_typ IN {_NEUE_FELD_TYPEN}")


def downgrade() -> None:
    op.drop_constraint("feld_typ_valid", "form_fields", type_="check")
    op.create_check_constraint("feld_typ_valid", "form_fields", f"feld_typ IN {_ALTE_FELD_TYPEN}")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON plan_symbole")
    op.drop_table("plan_symbole")
