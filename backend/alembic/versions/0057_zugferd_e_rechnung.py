"""ZUGFeRD-Rechnungen: fehlende Stammdaten fuer EN16931-Konformitaet.

Zwei neue, nullable Spalten -- keine neue Tabelle, keine RLS-Aenderung
noetig (rechnungen/kunden haben bereits eine mandant_isolation-Policy,
die automatisch fuer neue Spalten auf derselben Tabelle gilt).

kunden.ust_idnr: Umsatzsteuer-Identifikationsnummer des Kaeufers
(EN16931 BT-48) -- fehlte bisher komplett, ist aber nur bei
gewerblichen/oeffentlichen Kunden Pflicht (siehe
e_invoice_service.pruefe_en16931_vollstaendigkeit()).

rechnungen.xml_object_key: archiviert die beim Versand eingebettete
ZUGFeRD-XML separat abrufbar, analog zu pdf_object_key. Bleibt NULL,
wenn E-Rechnung fuer den Mandanten nicht aktiviert ist oder die
Vollstaendigkeitspruefung zum Versand-Zeitpunkt fehlschlug -- in
beiden Faellen wurde weiterhin nur ein normales PDF archiviert (siehe
rechnung_service._rechnung_dokument_bytes()).

Der Mandanten-Toggle "E-Rechnung aktivieren" und das Laendercode-Feld
brauchen bewusst KEINE Migration: Mandant.firmendaten ist ungetyptes
JSONB und wird beim Speichern gemerged statt ersetzt (siehe
mandant_einstellungen.py) -- genau wie ist_kleinunternehmer seinerzeit
ganz ohne Schema-Aenderung eingefuehrt wurde.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kunden", sa.Column("ust_idnr", sa.Text(), nullable=True))
    op.add_column("rechnungen", sa.Column("xml_object_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rechnungen", "xml_object_key")
    op.drop_column("kunden", "ust_idnr")
