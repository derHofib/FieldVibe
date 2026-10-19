"""Rechnungsarten: Abschlag, Schlussrechnung, Gutschrift, Rechnung aus Angebot.

rechnungen.rechnungsart unterscheidet 'rechnung', 'abschlag', 'schluss' und
'gutschrift'. Bestand und Storno-Belege bleiben 'rechnung' (ein Storno ist
weiterhin ueber ist_storno gekennzeichnet; seine Logik aendert sich nicht).

angebot_id verbindet Rechnungen mit dem Angebot, aus dem sie entstanden sind,
bezug_rechnung_id die Gutschrift mit ihrer Ursprungsrechnung.
gutschrift_grund haelt den Grund auf dem Beleg selbst -- es gibt kein
passendes Textfeld an der Rechnung, und ein GoBD-konformer Beleg muss ihn
unveraenderlich mitfuehren.

rechnung_positionen.abschlag_rechnung_id markiert die Abzugsposition einer
Schlussrechnung (welche Abschlagsrechnung sie anrechnet), bezug_position_id
die Gutschriftsposition (welche Originalposition sie zuruecknimmt). Beides
bewusst ohne UNIQUE-Index: eine stornierte Schlussrechnung behaelt ihre
Abzugspositionen, der Abschlag muss danach erneut anrechenbar sein -- die
Einmaligkeit prueft die Anwendung gegen nicht stornierte Belege.

Alle neuen Spalten sind nullable bzw. haben einen Default, kein Backfill. Die
Tabellen haben bereits Mandanten-RLS samt Trigger; neue Spalten brauchen keine
eigene Policy.

Revision ID: 0108
Revises: 0107
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0108"
down_revision: Union[str, None] = "0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_ANGEBOT = "fk_rechnungen_angebot_id_angebote"
_FK_BEZUG_RECHNUNG = "fk_rechnungen_bezug_rechnung_id_rechnungen"
_FK_ABSCHLAG = "fk_rechnung_positionen_abschlag_rechnung_id_rechnungen"
_FK_BEZUG_POSITION = "fk_rechnung_positionen_bezug_position_id_rechnung_positionen"
_IX_ANGEBOT = "ix_rechnungen_angebot_id"
_IX_BEZUG_RECHNUNG = "ix_rechnungen_bezug_rechnung_id"
_IX_ABSCHLAG = "ix_rechnung_positionen_abschlag_rechnung_id"
_IX_BEZUG_POSITION = "ix_rechnung_positionen_bezug_position_id"
# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CK_ART = "rechnungsart_valid"
_CK_GRUND = "gutschrift_grund_laenge"


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column("rechnungen", sa.Column("rechnungsart", sa.Text(), nullable=False, server_default="rechnung"))
    op.create_check_constraint(
        _CK_ART, "rechnungen", "rechnungsart IN ('rechnung', 'abschlag', 'schluss', 'gutschrift')"
    )
    op.add_column("rechnungen", sa.Column("angebot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(_FK_ANGEBOT, "rechnungen", "angebote", ["angebot_id"], ["id"])
    op.create_index(_IX_ANGEBOT, "rechnungen", ["angebot_id"])
    op.add_column("rechnungen", sa.Column("bezug_rechnung_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(_FK_BEZUG_RECHNUNG, "rechnungen", "rechnungen", ["bezug_rechnung_id"], ["id"])
    op.create_index(_IX_BEZUG_RECHNUNG, "rechnungen", ["bezug_rechnung_id"])
    op.add_column("rechnungen", sa.Column("gutschrift_grund", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CK_GRUND, "rechnungen", "gutschrift_grund IS NULL OR char_length(gutschrift_grund) <= 200"
    )

    op.add_column(
        "rechnung_positionen", sa.Column("abschlag_rechnung_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(_FK_ABSCHLAG, "rechnung_positionen", "rechnungen", ["abschlag_rechnung_id"], ["id"])
    op.create_index(_IX_ABSCHLAG, "rechnung_positionen", ["abschlag_rechnung_id"])
    op.add_column(
        "rechnung_positionen", sa.Column("bezug_position_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        _FK_BEZUG_POSITION, "rechnung_positionen", "rechnung_positionen", ["bezug_position_id"], ["id"]
    )
    op.create_index(_IX_BEZUG_POSITION, "rechnung_positionen", ["bezug_position_id"])


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_index(_IX_BEZUG_POSITION, table_name="rechnung_positionen")
    op.drop_constraint(_FK_BEZUG_POSITION, "rechnung_positionen", type_="foreignkey")
    op.drop_column("rechnung_positionen", "bezug_position_id")
    op.drop_index(_IX_ABSCHLAG, table_name="rechnung_positionen")
    op.drop_constraint(_FK_ABSCHLAG, "rechnung_positionen", type_="foreignkey")
    op.drop_column("rechnung_positionen", "abschlag_rechnung_id")

    op.drop_constraint(_CK_GRUND, "rechnungen", type_="check")
    op.drop_column("rechnungen", "gutschrift_grund")
    op.drop_index(_IX_BEZUG_RECHNUNG, table_name="rechnungen")
    op.drop_constraint(_FK_BEZUG_RECHNUNG, "rechnungen", type_="foreignkey")
    op.drop_column("rechnungen", "bezug_rechnung_id")
    op.drop_index(_IX_ANGEBOT, table_name="rechnungen")
    op.drop_constraint(_FK_ANGEBOT, "rechnungen", type_="foreignkey")
    op.drop_column("rechnungen", "angebot_id")
    op.drop_constraint(_CK_ART, "rechnungen", type_="check")
    op.drop_column("rechnungen", "rechnungsart")
