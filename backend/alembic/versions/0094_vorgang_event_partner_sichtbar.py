"""Partnerportal: vorgang_events.partner_sichtbar

Steuert, welche Kommentare ein Partner im Portal-Verlauf sieht -- eigene
Partner-Kommentare und im Office ausdruecklich "an Partner" freigegebene.
Bestehende Zeilen bleiben intern (Default false).

Revision ID: 0094
Revises: 0093
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vorgang_events",
        sa.Column("partner_sichtbar", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Bisherige Partner-Kommentare (Autor-Kennzeichen nur im payload) sind
    # ab jetzt im Portal-Verlauf sichtbar.
    op.execute(
        "UPDATE vorgang_events SET partner_sichtbar = true "
        "WHERE event_type = 'kommentar' AND author_user_id IS NULL "
        "AND payload ? 'partner_zugang_id'"
    )


def downgrade() -> None:
    op.drop_column("vorgang_events", "partner_sichtbar")
