"""Dauerauftraege: Modus (rollierend/fest) + Fruehstart-/Verzugstoleranz,
Vorgaenge behalten ihre dauerauftrag_id nicht mehr, wenn der Dauerauftrag
geloescht wird (Vorgaenge selbst bleiben unangetastet)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DAUERAUFTRAG_MODI = ("rollierend", "fest")


def upgrade() -> None:
    op.add_column(
        "dauerauftraege",
        sa.Column("modus", sa.Text(), nullable=False, server_default="rollierend"),
    )
    op.add_column("dauerauftraege", sa.Column("toleranz_frueh_tage", sa.SmallInteger(), nullable=True))
    op.add_column("dauerauftraege", sa.Column("toleranz_spaet_tage", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_dauerauftraege_modus_valid", "dauerauftraege", f"modus IN {DAUERAUFTRAG_MODI}"
    )
    op.create_check_constraint(
        "ck_dauerauftraege_toleranz_frueh_positiv",
        "dauerauftraege",
        "toleranz_frueh_tage IS NULL OR toleranz_frueh_tage >= 0",
    )
    op.create_check_constraint(
        "ck_dauerauftraege_toleranz_spaet_positiv",
        "dauerauftraege",
        "toleranz_spaet_tage IS NULL OR toleranz_spaet_tage >= 0",
    )

    # Ein geloeschter Dauerauftrag soll seine bereits erzeugten Vorgaenge
    # nicht mitreissen -- die bleiben als ganz normale, abgeschlossene (oder
    # noch offene) Vorgaenge bestehen, verlieren nur die Rueckverknuepfung.
    op.drop_constraint("fk_vorgaenge_dauerauftrag_id_dauerauftraege", "vorgaenge", type_="foreignkey")
    op.create_foreign_key(
        "fk_vorgaenge_dauerauftrag_id_dauerauftraege",
        "vorgaenge",
        "dauerauftraege",
        ["dauerauftrag_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_vorgaenge_dauerauftrag_id_dauerauftraege", "vorgaenge", type_="foreignkey")
    op.create_foreign_key(
        "fk_vorgaenge_dauerauftrag_id_dauerauftraege",
        "vorgaenge",
        "dauerauftraege",
        ["dauerauftrag_id"],
        ["id"],
    )

    op.drop_constraint("ck_dauerauftraege_toleranz_spaet_positiv", "dauerauftraege", type_="check")
    op.drop_constraint("ck_dauerauftraege_toleranz_frueh_positiv", "dauerauftraege", type_="check")
    op.drop_constraint("ck_dauerauftraege_modus_valid", "dauerauftraege", type_="check")
    op.drop_column("dauerauftraege", "toleranz_spaet_tage")
    op.drop_column("dauerauftraege", "toleranz_frueh_tage")
    op.drop_column("dauerauftraege", "modus")
