"""DATEV: feste Personenkonten fuer Kunden (Debitoren) und Lieferanten (Kreditoren).

Bisher wurde das Konto im Export aus crc32(ID) abgeleitet -- bei 9000 moeglichen
Werten kollidieren zwei Kunden schon bei wenigen hundert Datensaetzen (Geburtstags-
paradox). Jetzt traegt der Stammsatz sein Konto selbst; fehlt es, vergibt der
Export es einmalig (datev_service) und es bleibt danach stabil.

Das Konto ist je Mandant eindeutig, aber nur wenn gesetzt (Teil-Index) -- auch
ueber Papierkorb-Zeilen hinweg, denn alte Belege verweisen weiter darauf. Kein
Backfill: die alten crc32-Konten waren nie persistiert und wegen der fehlenden
Berater-/Mandantennummer (vorher stilles Default 1001/1) nie importfaehig.

Die Tabellen haben bereits Mandanten-RLS samt Trigger; neue Spalten brauchen
keine eigene Policy.

Revision ID: 0110
Revises: 0109
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0110"
down_revision: Union[str, None] = "0109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CK_KUNDE = "debitorenkonto_format"
_CK_LIEFERANT = "kreditorenkonto_format"
_UQ_KUNDE = "uq_kunden_mandant_debitorenkonto"
_UQ_LIEFERANT = "uq_lieferanten_mandant_kreditorenkonto"


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column("kunden", sa.Column("debitorenkonto", sa.Text(), nullable=True))
    op.create_check_constraint(_CK_KUNDE, "kunden", "debitorenkonto IS NULL OR debitorenkonto ~ '^[0-9]{5,9}$'")
    op.create_index(
        _UQ_KUNDE,
        "kunden",
        ["mandant_id", "debitorenkonto"],
        unique=True,
        postgresql_where=sa.text("debitorenkonto IS NOT NULL"),
    )
    op.add_column("lieferanten", sa.Column("kreditorenkonto", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CK_LIEFERANT, "lieferanten", "kreditorenkonto IS NULL OR kreditorenkonto ~ '^[0-9]{5,9}$'"
    )
    op.create_index(
        _UQ_LIEFERANT,
        "lieferanten",
        ["mandant_id", "kreditorenkonto"],
        unique=True,
        postgresql_where=sa.text("kreditorenkonto IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_index(_UQ_LIEFERANT, table_name="lieferanten")
    op.drop_constraint(_CK_LIEFERANT, "lieferanten", type_="check")
    op.drop_column("lieferanten", "kreditorenkonto")
    op.drop_index(_UQ_KUNDE, table_name="kunden")
    op.drop_constraint(_CK_KUNDE, "kunden", type_="check")
    op.drop_column("kunden", "debitorenkonto")
