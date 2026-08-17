"""Pruefzyklus: waehlbare Intervall-Einheit (Tage/Monate/Stunden) statt
fest auf Monate begrenzt. intervall_monate wird zu intervall_wert +
intervall_einheit; letzte_pruefung_am/naechste_pruefung_am wechseln von
Datum auf Zeitstempel, damit sich auch Stunden-Intervalle abbilden lassen.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pruefzyklen", sa.Column("intervall_wert", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "pruefzyklen",
        sa.Column("intervall_einheit", sa.Text(), nullable=False, server_default="monat"),
    )
    op.execute("UPDATE pruefzyklen SET intervall_wert = intervall_monate")
    op.alter_column("pruefzyklen", "intervall_wert", nullable=False)

    op.drop_constraint(op.f("ck_pruefzyklen_intervall_positiv"), "pruefzyklen", type_="check")
    op.drop_column("pruefzyklen", "intervall_monate")
    op.create_check_constraint(
        op.f("ck_pruefzyklen_intervall_positiv"), "pruefzyklen", "intervall_wert > 0"
    )
    op.create_check_constraint(
        op.f("ck_pruefzyklen_einheit_valid"),
        "pruefzyklen",
        "intervall_einheit IN ('tag', 'monat', 'stunde')",
    )

    op.alter_column(
        "pruefzyklen",
        "letzte_pruefung_am",
        type_=sa.TIMESTAMP(timezone=True),
        postgresql_using="(letzte_pruefung_am::timestamp AT TIME ZONE 'UTC')",
    )
    op.alter_column(
        "pruefzyklen",
        "naechste_pruefung_am",
        type_=sa.TIMESTAMP(timezone=True),
        nullable=False,
        postgresql_using="(naechste_pruefung_am::timestamp AT TIME ZONE 'UTC')",
    )


def downgrade() -> None:
    op.alter_column(
        "pruefzyklen",
        "naechste_pruefung_am",
        type_=sa.Date(),
        nullable=False,
        postgresql_using="(naechste_pruefung_am AT TIME ZONE 'UTC')::date",
    )
    op.alter_column(
        "pruefzyklen",
        "letzte_pruefung_am",
        type_=sa.Date(),
        postgresql_using="(letzte_pruefung_am AT TIME ZONE 'UTC')::date",
    )

    op.drop_constraint(op.f("ck_pruefzyklen_einheit_valid"), "pruefzyklen", type_="check")
    op.drop_constraint(op.f("ck_pruefzyklen_intervall_positiv"), "pruefzyklen", type_="check")
    op.add_column(
        "pruefzyklen", sa.Column("intervall_monate", sa.SmallInteger(), nullable=True)
    )
    op.execute("UPDATE pruefzyklen SET intervall_monate = intervall_wert")
    op.alter_column("pruefzyklen", "intervall_monate", nullable=False)
    op.create_check_constraint(
        op.f("ck_pruefzyklen_intervall_positiv"), "pruefzyklen", "intervall_monate > 0"
    )
    op.drop_column("pruefzyklen", "intervall_einheit")
    op.drop_column("pruefzyklen", "intervall_wert")
