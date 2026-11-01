"""Token-Widerruf: token_version an users, kundenportal_zugaenge, partner_zugaenge.

Access-/Refresh-Tokens tragen den Zaehler als Claim "tv"; wird er am Account
erhoeht (Sperren, Passwortwechsel, "ueberall abmelden"), sind alle bisher
ausgestellten Tokens ungueltig. Reine Spalten, keine neuen Tabellen -- die
bestehenden RLS-Policies/Trigger gelten unveraendert.

Revision ID: 0096
Revises: 0095
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0096"
down_revision: Union[str, None] = "0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLEN = ("users", "kundenportal_zugaenge", "partner_zugaenge")


def upgrade() -> None:
    for tabelle in _TABELLEN:
        op.add_column(
            tabelle,
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for tabelle in reversed(_TABELLEN):
        op.drop_column(tabelle, "token_version")
