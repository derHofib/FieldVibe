"""Selbst-Zuweisung von Vorgaengen: jeder Mitarbeiter (unabhaengig von
mandant_admin/Techniker) soll einen Vorgang per Klick "uebernehmen" koennen
(siehe app/api/routes/vorgaenge.py:uebernehmen). Zwei neue Spalten:

- vorgaenge.zugewiesener_user_id: wer ist gerade fuer diesen Vorgang
  zustaendig (nullable, kein Pflichtfeld -- viele Vorgaenge bleiben
  unzugewiesen, z.B. abgeschlossene Altbestaende).
- account_typen.darf_vorgaenge_selbst_uebernehmen: pro Account-Typ
  einstellbar, ob dessen Nutzer sich selbst zuweisen duerfen, oder ob sie
  auf eine manuelle Zuweisung durch mandant_admin/Dispo warten muessen
  (siehe app/services/rechte_service.py:darf_vorgang_selbst_uebernehmen) --
  analog zum bestehenden Schalter AccountTyp.nur_zugewiesene_kunden.
  Default false, damit bestehende Account-Typen sich nicht ungefragt neues
  Verhalten einhandeln.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vorgaenge",
        sa.Column("zugewiesener_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_vorgaenge_zugewiesener_user_id_users",
        "vorgaenge",
        "users",
        ["zugewiesener_user_id"],
        ["id"],
    )
    op.add_column(
        "account_typen",
        sa.Column(
            "darf_vorgaenge_selbst_uebernehmen",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("account_typen", "darf_vorgaenge_selbst_uebernehmen")
    op.drop_constraint("fk_vorgaenge_zugewiesener_user_id_users", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "zugewiesener_user_id")
