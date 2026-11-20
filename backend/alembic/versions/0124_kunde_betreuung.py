"""Kundenbetreuung: Hauptbetreuer an kunde_zuweisungen.

Jeder aktive Mitarbeiter kann Betreuer eines Kunden sein, einer davon
optional Hauptbetreuer. Der partielle Unique-Index erzwingt "hoechstens ein
Hauptbetreuer je Kunde" auch gegen konkurrierende Requests.

Backfill: Kunden mit genau einer Zuweisung -- der bisherige Techniker ist
fachlich der Hauptbetreuer. Laeuft in rls_fuer_backfill_aufheben, weil die
Migration ohne app.current_mandant als Tabelleneigentuemerin mit FORCE RLS
sonst keine Zeile trifft.

Revision ID: 0124
Revises: 0123
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.migrations_helfer import rls_fuer_backfill_aufheben

revision: str = "0124"
down_revision: Union[str, None] = "0123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kunde_zuweisungen",
        sa.Column("hauptbetreuer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_kunde_zuweisungen_haupt",
        "kunde_zuweisungen",
        ["kunde_id"],
        unique=True,
        postgresql_where=sa.text("hauptbetreuer"),
    )

    with rls_fuer_backfill_aufheben("kunde_zuweisungen"):
        op.execute(
            "UPDATE kunde_zuweisungen SET hauptbetreuer = true "
            "WHERE kunde_id IN ("
            "SELECT kunde_id FROM kunde_zuweisungen GROUP BY kunde_id HAVING count(*) = 1)"
        )


def downgrade() -> None:
    op.drop_index("uq_kunde_zuweisungen_haupt", table_name="kunde_zuweisungen")
    op.drop_column("kunde_zuweisungen", "hauptbetreuer")
