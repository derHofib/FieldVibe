"""Modul-Flags pro Mandant (Super-Admin-Menue): deaktivierte_module ist eine
JSONB-Liste von Modul-Schluesseln, die fuer diesen Mandanten abgeschaltet
sind. Opt-out statt Opt-in -- leere Liste (Default) heisst "alles an", ein
neues Modul ist also automatisch fuer alle bestehenden Mandanten aktiv,
ohne dass hier nachgepflegt werden muesste.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mandanten",
        sa.Column(
            "deaktivierte_module",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mandanten", "deaktivierte_module")
