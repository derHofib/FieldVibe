"""Fuegt Vorgang.erstellt_von (Mitarbeiter, der den Vorgang angelegt hat) und
Vorgang.faelligkeit_am (Faelligkeitsdatum fuer Feed-Filter/Priorisierung)
hinzu.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vorgaenge", sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_vorgaenge_erstellt_von_users"),
        "vorgaenge",
        "users",
        ["erstellt_von"],
        ["id"],
    )
    op.add_column(
        "vorgaenge", sa.Column("faelligkeit_am", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("idx_vorgaenge_faelligkeit_am"), "vorgaenge", ["mandant_id", "faelligkeit_am"]
    )


def downgrade() -> None:
    op.drop_index(op.f("idx_vorgaenge_faelligkeit_am"), table_name="vorgaenge")
    op.drop_column("vorgaenge", "faelligkeit_am")
    op.drop_constraint(op.f("fk_vorgaenge_erstellt_von_users"), "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "erstellt_von")
