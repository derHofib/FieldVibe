"""Fehlerberichte: Art (fehler | idee) und Freigabe-Zeitpunkt fuer Ideen.

freigegeben_am wird gesetzt, wenn der Super-Admin eine Idee auf 'gesichtet'
(= freigegeben) stellt; Ideen werden nur nach Freigabe umgesetzt.

Revision ID: 0099
Revises: 0098
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: Union[str, None] = "0098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fehlerberichte", sa.Column("art", sa.Text(), nullable=False, server_default="fehler"))
    op.add_column("fehlerberichte", sa.Column("freigegeben_am", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_check_constraint("art_valid", "fehlerberichte", "art IN ('fehler', 'idee')")
    op.create_index("ix_fehlerberichte_art_status", "fehlerberichte", ["art", "status"])


def downgrade() -> None:
    op.drop_index("ix_fehlerberichte_art_status", table_name="fehlerberichte")
    op.drop_constraint("art_valid", "fehlerberichte", type_="check")
    op.drop_column("fehlerberichte", "freigegeben_am")
    op.drop_column("fehlerberichte", "art")
