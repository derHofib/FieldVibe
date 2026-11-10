"""Nummernkreise fuer Kunden, Vorgaenge, Angebote und Bestellungen ueber
beleg_zaehler statt COUNT(*)+1.

Der Count sank, sobald ein Datensatz im Papierkorb endgueltig geloescht wurde
(papierkorb_service.purge) -- die naechste Nummer war dann schon vergeben und
der UniqueConstraint (mandant_id, nummer) schlug dauerhaft fehl. Die Zaehler
werden je Mandant und Belegart auf MAX(vorhandene Nummer) + 1 gesetzt; Nummern,
die nicht dem Muster '<Praefix>-<Ziffern>' folgen (manuell vergeben), werden
ignoriert. Soft-geloeschte Datensaetze zaehlen mit, sie halten ihre Nummer
weiterhin belegt. Mandanten ohne passende Nummer bekommen keine Zeile
(entspricht naechste_nummer = 1). Bestehende Zaehler (z.B. 'rechnung') bleiben
unberuehrt.

Revision ID: 0103
Revises: 0102
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: Union[str, None] = "0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (belegart, Tabelle, Nummernspalte, Praefix) -- Bezeichner sind feste
# Konstanten dieser Migration, nie Nutzereingaben.
_NUMMERNKREISE = (
    ("kunde", "kunden", "kundennummer", "K"),
    ("vorgang", "vorgaenge", "vorgangsnummer", "V"),
    ("angebot", "angebote", "angebotsnummer", "A"),
    ("bestellung", "bestellungen", "bestellnummer", "B"),
)


def initialisiere_zaehler(connection: sa.engine.Connection) -> None:
    # Max. 9 Ziffern: naechste_nummer ist ein Integer, eine absurd lange
    # manuelle Nummer duerfte den Cast nicht zum Ueberlauf bringen.
    for belegart, tabelle, spalte, praefix in _NUMMERNKREISE:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO beleg_zaehler (mandant_id, belegart, naechste_nummer)
                SELECT mandant_id, :belegart, MAX(split_part({spalte}, '-', 2)::integer) + 1
                FROM {tabelle}
                WHERE {spalte} ~ :muster
                GROUP BY mandant_id
                ON CONFLICT (mandant_id, belegart) DO NOTHING
                """
            ),
            {"belegart": belegart, "muster": f"^{praefix}-[0-9]{{1,9}}$"},
        )


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    initialisiere_zaehler(op.get_bind())


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.execute(
        "DELETE FROM beleg_zaehler WHERE belegart IN ('kunde', 'vorgang', 'angebot', 'bestellung')"
    )
