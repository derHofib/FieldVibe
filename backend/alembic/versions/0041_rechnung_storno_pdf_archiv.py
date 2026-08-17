"""Stornorechnung als eigener Beleg statt reinem Status-Flip (ist_storno +
storniert_rechnung_id) und Archivierung des tatsaechlich versendeten PDFs
(pdf_object_key) -- GoBD verbietet, eine einmal versendete Rechnung
nachtraeglich zu aendern oder zu loeschen bzw. deren Abbild sich durch
spaetere Firmendaten-Aenderungen veraendern zu lassen.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rechnungen",
        sa.Column("ist_storno", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "rechnungen",
        sa.Column(
            "storniert_rechnung_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rechnungen.id"),
            nullable=True,
        ),
    )
    op.add_column("rechnungen", sa.Column("pdf_object_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rechnungen", "pdf_object_key")
    op.drop_column("rechnungen", "storniert_rechnung_id")
    op.drop_column("rechnungen", "ist_storno")
