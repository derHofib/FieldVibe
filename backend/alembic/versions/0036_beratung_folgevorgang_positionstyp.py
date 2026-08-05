"""Beratung/Planung-Workflow: MaterialBedarf bekommt einen neuen Status
"uebertragen" (fuer Bedarfe, die beim Abschluss einer Beratung auf einen
neu angelegten Folge-Vorgang umgehaengt wurden, aber am Ursprungs-Vorgang
zur Dokumentation stehen bleiben) plus eine Rueckverknuepfung zum
Original-Bedarf. Ausserdem bekommt eine Angebotsposition einen Typ
(Material/Arbeitszeit), damit man z.B. Beratungsstunden als eigene,
erkennbare Position neben uebernommenem Material eintragen kann.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_material_bedarfe_status_valid"), "material_bedarfe", type_="check")
    op.create_check_constraint(
        op.f("ck_material_bedarfe_status_valid"),
        "material_bedarfe",
        "status IN ('offen','bestellt','in_angebot','erhalten','storniert','uebertragen')",
    )
    op.add_column(
        "material_bedarfe",
        sa.Column("uebernommen_von_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_material_bedarfe_uebernommen_von_id_material_bedarfe"),
        "material_bedarfe",
        "material_bedarfe",
        ["uebernommen_von_id"],
        ["id"],
    )

    op.add_column(
        "angebot_positionen",
        sa.Column("positionstyp", sa.Text(), nullable=False, server_default="material"),
    )
    op.create_check_constraint(
        op.f("ck_angebot_positionen_positionstyp_valid"),
        "angebot_positionen",
        "positionstyp IN ('material','arbeitszeit')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_angebot_positionen_positionstyp_valid"), "angebot_positionen", type_="check"
    )
    op.drop_column("angebot_positionen", "positionstyp")

    op.drop_constraint(
        op.f("fk_material_bedarfe_uebernommen_von_id_material_bedarfe"),
        "material_bedarfe",
        type_="foreignkey",
    )
    op.drop_column("material_bedarfe", "uebernommen_von_id")
    op.drop_constraint(op.f("ck_material_bedarfe_status_valid"), "material_bedarfe", type_="check")
    op.create_check_constraint(
        op.f("ck_material_bedarfe_status_valid"),
        "material_bedarfe",
        "status IN ('offen','bestellt','in_angebot','erhalten','storniert')",
    )
