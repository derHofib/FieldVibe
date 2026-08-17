"""Fuegt "woche" als weitere waehlbare Pruefzyklus-Intervall-Einheit hinzu
(neben Tage/Monate/Stunden aus Migration 0028).

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_pruefzyklen_einheit_valid"), "pruefzyklen", type_="check")
    op.create_check_constraint(
        op.f("ck_pruefzyklen_einheit_valid"),
        "pruefzyklen",
        "intervall_einheit IN ('tag', 'woche', 'monat', 'stunde')",
    )


def downgrade() -> None:
    op.execute("UPDATE pruefzyklen SET intervall_einheit = 'tag' WHERE intervall_einheit = 'woche'")
    op.drop_constraint(op.f("ck_pruefzyklen_einheit_valid"), "pruefzyklen", type_="check")
    op.create_check_constraint(
        op.f("ck_pruefzyklen_einheit_valid"),
        "pruefzyklen",
        "intervall_einheit IN ('tag', 'monat', 'stunde')",
    )
