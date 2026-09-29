"""Material wird wie Zeit gesperrt/freigegeben.

material_verwendungen bekommt abrechnungsstatus/abgerechnet_rechnung_id
(Spiegel zu zeiterfassung.buchungsstatus/abgerechnet_rechnung_id),
rechnung_positionen merkt sich das Material, damit das Entfernen der Position
genau dessen Verwendungen wieder freigibt. Kein Backfill: bisherige
Material-Positionen haben nie etwas gesperrt.

Revision ID: 0089
Revises: 0088
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0089"
down_revision: Union[str, None] = "0088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "material_verwendungen",
        sa.Column("abrechnungsstatus", sa.Text(), nullable=False, server_default="offen"),
    )
    op.create_check_constraint(
        "ck_material_verwendungen_abrechnungsstatus_valid",
        "material_verwendungen",
        "abrechnungsstatus IN ('offen', 'abgerechnet')",
    )
    op.add_column(
        "material_verwendungen",
        sa.Column("abgerechnet_rechnung_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_material_verwendungen_abgerechnet_rechnung_id_rechnungen",
        "material_verwendungen",
        "rechnungen",
        ["abgerechnet_rechnung_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_material_verwendungen_abgerechnet_rechnung_id",
        "material_verwendungen",
        ["abgerechnet_rechnung_id"],
    )

    op.add_column(
        "rechnung_positionen",
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rechnung_positionen_material_id_material",
        "rechnung_positionen",
        "material",
        ["material_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_rechnung_positionen_material_id", "rechnung_positionen", ["material_id"])


def downgrade() -> None:
    op.drop_index("ix_rechnung_positionen_material_id", table_name="rechnung_positionen")
    op.drop_constraint("fk_rechnung_positionen_material_id_material", "rechnung_positionen", type_="foreignkey")
    op.drop_column("rechnung_positionen", "material_id")

    op.drop_index("ix_material_verwendungen_abgerechnet_rechnung_id", table_name="material_verwendungen")
    op.drop_constraint(
        "fk_material_verwendungen_abgerechnet_rechnung_id_rechnungen", "material_verwendungen", type_="foreignkey"
    )
    op.drop_column("material_verwendungen", "abgerechnet_rechnung_id")
    op.drop_constraint("ck_material_verwendungen_abrechnungsstatus_valid", "material_verwendungen", type_="check")
    op.drop_column("material_verwendungen", "abrechnungsstatus")
