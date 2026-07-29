"""Nacharbeit: vorgaenge.client_uuid fuer Offline-Idempotenz bei Neuanlage

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vorgaenge", sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_vorgaenge_client_uuid", "vorgaenge", ["client_uuid"])


def downgrade() -> None:
    op.drop_constraint("uq_vorgaenge_client_uuid", "vorgaenge", type_="unique")
    op.drop_column("vorgaenge", "client_uuid")
