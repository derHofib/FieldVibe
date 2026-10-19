"""Steuergruende je Rechnungsposition und 13b-Nachweis beim Kunden.

Z (0 %), E (steuerfrei) und AE (Reverse Charge, Paragraph 13b UStG) brauchen
einen Grund, der auf Rechnung und E-Rechnung als Hinweistext erscheint. Der
Schluessel steht in rechnung_positionen.steuer_grund (Katalog:
steuer_service.STEUER_GRUENDE); nur 'sonstige_befreiung' traegt zusaetzlich
einen freien Text. Backfill: bei Kleinunternehmer-Mandanten sind alle
E-Positionen 'kleinunternehmer_19'. Sonstiger Altbestand mit E/0 bleibt ohne
Grund zulaessig (NULL) -- vor dem Versand wird er geprueft (nicht in der DB,
weil Entwuerfe noch unvollstaendig sein duerfen).

kunden.ust_13b_nachweis_bis ist das Ablaufdatum der Bescheinigung USt 1 TG des
Leistungsempfaengers (Paragraph 13b Abs. 2 Nr. 4 UStG).

Beide Tabellen haben bereits Mandanten-RLS samt Trigger (Migrationen davor);
neue Spalten brauchen keine eigene Policy.

Revision ID: 0105
Revises: 0104
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0105"
down_revision: Union[str, None] = "0104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLE = "rechnung_positionen"
# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CHECKS = (
    (
        "steuer_grund_valid",
        "steuer_grund IS NULL OR steuer_grund IN "
        "('pv_12_3', 'reverse_charge_13b', 'kleinunternehmer_19', 'sonstige_befreiung')",
    ),
    ("steuer_grund_text_laenge", "steuer_grund_text IS NULL OR char_length(steuer_grund_text) <= 200"),
)


def backfill_kleinunternehmer(connection: sa.engine.Connection) -> None:
    connection.execute(
        sa.text(
            f"""
            UPDATE {_TABELLE} AS p
            SET steuer_grund = 'kleinunternehmer_19'
            FROM mandanten AS m
            WHERE m.id = p.mandant_id
              AND p.steuer_kategorie = 'E'
              AND m.firmendaten ->> 'ist_kleinunternehmer' = 'true'
            """
        )
    )


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column(_TABELLE, sa.Column("steuer_grund", sa.Text(), nullable=True))
    op.add_column(_TABELLE, sa.Column("steuer_grund_text", sa.Text(), nullable=True))
    backfill_kleinunternehmer(op.get_bind())
    for name, bedingung in _CHECKS:
        op.create_check_constraint(name, _TABELLE, bedingung)
    op.add_column("kunden", sa.Column("ust_13b_nachweis_bis", sa.Date(), nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_column("kunden", "ust_13b_nachweis_bis")
    for name, _ in reversed(_CHECKS):
        op.drop_constraint(name, _TABELLE, type_="check")
    op.drop_column(_TABELLE, "steuer_grund_text")
    op.drop_column(_TABELLE, "steuer_grund")
