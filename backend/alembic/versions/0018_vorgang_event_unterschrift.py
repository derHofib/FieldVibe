"""Digitale Unterschrift des Kunden als neuer VorgangEvent-Typ
("unterschrift") -- speichert wie "foto" nur einen S3-Key im payload,
keine eigene Spalte/Tabelle noetig.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TYPEN = (
    "kommentar", "status_change", "foto", "dokument", "mangel",
    "angebot", "material", "zeit_start", "zeit_stop", "termin",
    "rechnung_status", "system",
)
_NEW_TYPEN = _OLD_TYPEN + ("unterschrift",)


def upgrade() -> None:
    op.drop_constraint(
        "ck_vorgang_events_event_type_valid", "vorgang_events", type_="check"
    )
    op.create_check_constraint(
        "ck_vorgang_events_event_type_valid",
        "vorgang_events",
        f"event_type IN {_NEW_TYPEN}",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_vorgang_events_event_type_valid", "vorgang_events", type_="check"
    )
    op.create_check_constraint(
        "ck_vorgang_events_event_type_valid",
        "vorgang_events",
        f"event_type IN {_OLD_TYPEN}",
    )
