"""Folge-Auftrag als eigenstaendige Aktion + Wiedervorlage bei wartet_kunde.

Loest die bisherige Folge-Vorgang-Erzeugung vom Abschliessen ab (bisher nur
beim PATCH-Abschluss eines Beratungs-Vorgangs moeglich, siehe close_vorgang
in app/services/vorgang_completion_service.py) -- ab jetzt ueber eine
eigene Route in jedem Status der Quelle aufrufbar, dafuer sind aber keine
neuen Spalten noetig (parent_vorgang_id existiert bereits).

vorgaenge.wiedervorlage_am: Erinnerungszeitpunkt fuer status=wartet_kunde,
vom Scheduler ausgewertet und nach dem Feuern wieder auf NULL gesetzt
(Einmal-Trigger, gleiches Muster wie Pruefzyklus.offener_vorgang_id).

mandanten.wiedervorlage_standard_tage: NULL = globaler Default (14 Tage),
analog zu mandanten.scheduler_stunde_utc.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vorgaenge", sa.Column("wiedervorlage_am", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "mandanten",
        sa.Column("wiedervorlage_standard_tage", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_mandanten_wiedervorlage_standard_tage_valid"),
        "mandanten",
        "wiedervorlage_standard_tage IS NULL OR wiedervorlage_standard_tage > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_mandanten_wiedervorlage_standard_tage_valid"), "mandanten", type_="check"
    )
    op.drop_column("mandanten", "wiedervorlage_standard_tage")
    op.drop_column("vorgaenge", "wiedervorlage_am")
