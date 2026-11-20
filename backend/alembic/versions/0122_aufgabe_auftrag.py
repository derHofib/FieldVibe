"""Meine Aufgaben: Aufgabe kann direkt an einem Auftrag haengen.

- projekt_aufgaben.auftrag_id (FK auftraege, ON DELETE SET NULL) + Index.
- ck_projekt_aufgaben_auftrag_oder_vorgang: entweder Auftrag oder Vorgang, nie
  beides -- der Auftrag eines Vorgangs ergibt sich ueber den Vorgang selbst.
- gespeicherte_filter: Entitaet 'aufgaben' zulaessig (Check-Constraint erweitert).

Keine neue Tabelle, die bestehende RLS-Policy/Trigger gelten unveraendert.

Downgrade: gespeicherte Filter der Entitaet 'aufgaben' werden geloescht (wie in
0055), bevor der engere Constraint zurueckkommt; das geht auf der RLS-Tabelle
nur im Backfill-Helfer.

Revision ID: 0122
Revises: 0121
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.migrations_helfer import rls_fuer_backfill_aufheben

revision: str = "0122"
down_revision: Union[str, None] = "0121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENTITAETEN_ALT = ("vorgaenge", "anlagen", "kunden", "standorte", "rechnungen")
_ENTITAETEN_NEU = _ENTITAETEN_ALT + ("aufgaben",)


def _filter_constraint(entitaeten: tuple[str, ...]) -> None:
    op.drop_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"), "gespeicherte_filter", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_gespeicherte_filter_entitaet_valid"),
        "gespeicherte_filter",
        f"entitaet IN {entitaeten}",
    )


def upgrade() -> None:
    op.add_column(
        "projekt_aufgaben",
        sa.Column(
            "auftrag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auftraege.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_projekt_aufgaben_auftrag_id", "projekt_aufgaben", ["auftrag_id"])
    op.create_check_constraint(
        op.f("ck_projekt_aufgaben_auftrag_oder_vorgang"),
        "projekt_aufgaben",
        "auftrag_id IS NULL OR vorgang_id IS NULL",
    )
    _filter_constraint(_ENTITAETEN_NEU)


def downgrade() -> None:
    with rls_fuer_backfill_aufheben("gespeicherte_filter"):
        op.execute("DELETE FROM gespeicherte_filter WHERE entitaet = 'aufgaben'")
    _filter_constraint(_ENTITAETEN_ALT)

    op.drop_constraint(
        op.f("ck_projekt_aufgaben_auftrag_oder_vorgang"), "projekt_aufgaben", type_="check"
    )
    op.drop_index("ix_projekt_aufgaben_auftrag_id", table_name="projekt_aufgaben")
    op.drop_column("projekt_aufgaben", "auftrag_id")
