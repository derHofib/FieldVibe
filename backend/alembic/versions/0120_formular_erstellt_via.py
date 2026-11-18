"""Herkunft von Formular-Vorlagen und Ausfuellungen (Konzept formulare, Etappe A).

- form_schemas.erstellt_via, form_submissions.erstellt_via: 'app' oder 'ki' (Claude ueber den
  MCP-Server). NULL = vor dieser Migration angelegt und gilt als 'app'; kein Backfill, weil die
  Herkunft alter Eintraege nicht rekonstruierbar ist (nur das Audit-Log kennt sie, nicht verlaesslich).

Keine neue Tabelle: die bestehenden RLS-Policies/Trigger sind nicht spaltenspezifisch und
gelten unveraendert.

Revision ID: 0120
Revises: 0119
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0120"
down_revision: Union[str, None] = "0119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLEN = ("form_schemas", "form_submissions")


def upgrade() -> None:
    for tabelle in _TABELLEN:
        op.add_column(tabelle, sa.Column("erstellt_via", sa.Text(), nullable=True))
        op.create_check_constraint(
            f"ck_{tabelle}_erstellt_via", tabelle, "erstellt_via IS NULL OR erstellt_via IN ('app', 'ki')"
        )


def downgrade() -> None:
    for tabelle in _TABELLEN:
        op.drop_constraint(f"ck_{tabelle}_erstellt_via", tabelle, type_="check")
        op.drop_column(tabelle, "erstellt_via")
