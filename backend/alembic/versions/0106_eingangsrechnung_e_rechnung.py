"""E-Rechnung im Rechnungseingang: Original-XML, Pruefsumme, Syntax, Importhinweis.

Seit 01.01.2025 muss jeder Betrieb E-Rechnungen empfangen koennen. Bei einer
E-Rechnung ist die XML der Beleg im Sinne des BMF-Schreibens vom 14.07.2025:
sie wird byte-identisch in S3 archiviert (xml_object_key) und mit SHA-256
gesichert (xml_sha256, 64 Hex-Zeichen) -- nie neu erzeugt oder veraendert. Ein
Hybrid-PDF (ZUGFeRD/Factur-X) liegt zusaetzlich als beleg_object_key vor.

e_rechnung_syntax ist 'cii' oder 'ubl' (NULL = kein E-Rechnungs-Import).
import_hinweis sammelt Punkte, die ein Mensch pruefen soll (z. B. mehrere
Steuersaetze, die das Modell mit einem mwst_satz je Beleg nicht abbildet).

Alle Spalten sind nullable, Altbestand bleibt unveraendert. Die Tabelle hat
bereits Mandanten-RLS samt Trigger; neue Spalten brauchen keine eigene Policy.

Revision ID: 0106
Revises: 0105
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0106"
down_revision: Union[str, None] = "0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLE = "eingangsrechnungen"
# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CHECKS = (
    ("e_rechnung_syntax_valid", "e_rechnung_syntax IS NULL OR e_rechnung_syntax IN ('cii', 'ubl')"),
    ("xml_sha256_format", "xml_sha256 IS NULL OR xml_sha256 ~ '^[0-9a-f]{64}$'"),
)


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column(_TABELLE, sa.Column("xml_object_key", sa.Text(), nullable=True))
    op.add_column(_TABELLE, sa.Column("xml_sha256", sa.Text(), nullable=True))
    op.add_column(_TABELLE, sa.Column("e_rechnung_syntax", sa.Text(), nullable=True))
    op.add_column(_TABELLE, sa.Column("import_hinweis", sa.Text(), nullable=True))
    for name, bedingung in _CHECKS:
        op.create_check_constraint(name, _TABELLE, bedingung)


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    for name, _ in reversed(_CHECKS):
        op.drop_constraint(name, _TABELLE, type_="check")
    op.drop_column(_TABELLE, "import_hinweis")
    op.drop_column(_TABELLE, "e_rechnung_syntax")
    op.drop_column(_TABELLE, "xml_sha256")
    op.drop_column(_TABELLE, "xml_object_key")
