"""rechnung_positionen.lv_position_id.

Eine "leistung"-Position fasst SVS-gekoppelte Zeit (zeiterfassung.
lv_position_id) und LV-Verwendungen zusammen. Damit das Uebernehmen die Zeit
sperrt und das Entfernen genau die Zeilen dieser LV-Position wieder freigibt,
merkt sich die Position ihre LV-Position. Kein Backfill: bisherige
"leistung"-Positionen haben nie Zeit gesperrt.

Revision ID: 0088
Revises: 0087
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0088"
down_revision: Union[str, None] = "0087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rechnung_positionen",
        sa.Column("lv_position_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rechnung_positionen_lv_position_id_lv_positionen",
        "rechnung_positionen",
        "leistungsverzeichnis_positionen",
        ["lv_position_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_rechnung_positionen_lv_position_id", "rechnung_positionen", ["lv_position_id"])


def downgrade() -> None:
    op.drop_index("ix_rechnung_positionen_lv_position_id", table_name="rechnung_positionen")
    op.drop_constraint(
        "fk_rechnung_positionen_lv_position_id_lv_positionen", "rechnung_positionen", type_="foreignkey"
    )
    op.drop_column("rechnung_positionen", "lv_position_id")
