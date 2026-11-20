"""Kunden-Referenz ("Ihr Zeichen") und Leistungsort an Rechnung/Angebot, Kontakte an Portalanfragen (Etappe B).

- rechnungen/angebote: kunden_referenz, leistungsort (jsonb-Snapshot {bezeichnung, strasse, plz, ort, land}).
- vorgang_anfragen: einheit, kunden_referenz, vor_ort_kontakte (jsonb-Liste, bis zur Annahme der Anfrage;
  danach wandern die Daten in die Tabelle vor_ort_kontakte und die Liste wird geleert).

Kein Backfill: alles ist neu und nullable bzw. hat einen Default.

Revision ID: 0126
Revises: 0125
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0126"
down_revision: Union[str, None] = "0125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for tabelle in ("rechnungen", "angebote"):
        op.add_column(tabelle, sa.Column("kunden_referenz", sa.Text(), nullable=True))
        op.add_column(tabelle, sa.Column("leistungsort", postgresql.JSONB(), nullable=True))
    op.add_column("vorgang_anfragen", sa.Column("einheit", sa.Text(), nullable=True))
    op.add_column("vorgang_anfragen", sa.Column("kunden_referenz", sa.Text(), nullable=True))
    op.add_column(
        "vorgang_anfragen",
        sa.Column("vor_ort_kontakte", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("vorgang_anfragen", "vor_ort_kontakte")
    op.drop_column("vorgang_anfragen", "kunden_referenz")
    op.drop_column("vorgang_anfragen", "einheit")
    for tabelle in ("angebote", "rechnungen"):
        op.drop_column(tabelle, "leistungsort")
        op.drop_column(tabelle, "kunden_referenz")
