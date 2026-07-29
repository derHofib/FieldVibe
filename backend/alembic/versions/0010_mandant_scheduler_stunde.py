"""Nacharbeit: mandanten.scheduler_stunde_utc (pro Mandant konfigurierbare
Scheduler-Uhrzeit)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mandanten", sa.Column("scheduler_stunde_utc", sa.SmallInteger(), nullable=True)
    )
    op.create_check_constraint(
        "ck_mandanten_scheduler_stunde_utc_valid",
        "mandanten",
        "scheduler_stunde_utc IS NULL OR (scheduler_stunde_utc >= 0 AND scheduler_stunde_utc <= 23)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_mandanten_scheduler_stunde_utc_valid", "mandanten", type_="check")
    op.drop_column("mandanten", "scheduler_stunde_utc")
