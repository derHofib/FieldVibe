"""Gantt-Dispo (siehe app/models/termin.py): zwei optionale Zusatzfelder auf
termine fuer eine realistischere Zeitplanung -- Fahrzeit zur Anlage und
Pause direkt nach dem Termin, beide in Minuten. NULL = kein Zuschlag
(bisheriges Verhalten), bestehende Termine bleiben also unveraendert.

Revision ID: 0066
Revises: 0065
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("termine", sa.Column("fahrzeit_minuten", sa.Integer(), nullable=True))
    op.add_column("termine", sa.Column("pause_minuten", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("termine", "pause_minuten")
    op.drop_column("termine", "fahrzeit_minuten")
