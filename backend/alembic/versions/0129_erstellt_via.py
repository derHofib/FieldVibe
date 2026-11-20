"""Herkunft 'per KI' an Vorgaengen, Auftraegen, Projekten, Angeboten, Rechnungen und Terminen
(MCP-Ausbau Etappe A).

Spalte erstellt_via ('app' | 'ki'), wie schon bei Formularen (0120) und Telefonaten (0121). Gesetzt
wird sie serverseitig beim Anlegen aus dem Token (auth.via == "mcp"). Kein Backfill: der
Server-Default 'app' gilt fuer den Altbestand, die Spalte ist NOT NULL ohne Tabellen-Rewrite.

Keine neue Tabelle, RLS-Policies/Trigger gelten unveraendert.

Downgrade: Constraint und Spalte weg.

Revision ID: 0129
Revises: 0128
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0129"
down_revision: Union[str, None] = "0128"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLEN = ("vorgaenge", "auftraege", "projekte", "angebote", "rechnungen", "termine")


def upgrade() -> None:
    for tabelle in _TABELLEN:
        op.add_column(tabelle, sa.Column("erstellt_via", sa.Text(), nullable=False, server_default="app"))
        op.create_check_constraint("erstellt_via_valid", tabelle, "erstellt_via IN ('app', 'ki')")


def downgrade() -> None:
    for tabelle in reversed(_TABELLEN):
        op.drop_constraint("erstellt_via_valid", tabelle, type_="check")
        op.drop_column(tabelle, "erstellt_via")
