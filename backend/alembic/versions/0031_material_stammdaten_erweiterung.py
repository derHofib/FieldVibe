"""Material-Stammdaten erweitern: Artikelnummer + Bestell-Link fuer eine
bessere Beschreibung des Artikels, und "material" als weiterer
Tag-Entity-Typ, damit sich Material genauso wie Kunde/Anlage/Vorgang
mit Tags filtern laesst.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("material", sa.Column("artikelnummer", sa.Text(), nullable=True))
    op.add_column("material", sa.Column("bestell_url", sa.Text(), nullable=True))

    op.drop_constraint(
        op.f("ck_tag_assignments_entity_type_valid"), "tag_assignments", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_tag_assignments_entity_type_valid"),
        "tag_assignments",
        "entity_type IN ('kunde','anlage','vorgang','material')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_tag_assignments_entity_type_valid"), "tag_assignments", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_tag_assignments_entity_type_valid"),
        "tag_assignments",
        "entity_type IN ('kunde','anlage','vorgang')",
    )

    op.drop_column("material", "bestell_url")
    op.drop_column("material", "artikelnummer")
