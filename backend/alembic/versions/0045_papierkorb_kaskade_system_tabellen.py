"""Vier bewusst NICHT im Papierkorb gefuehrte "System-/Log-Tabellen" (siehe
Migration 0032: vorgang_events, highlights, zeiterfassungen,
kundenportal_zugaenge) hatten keine ON DELETE CASCADE auf ihre FK zu einer
Papierkorb-Entitaet -- das endgueltige Loeschen (purge()) eines Kunden oder
Vorgangs im Papierkorb scheiterte deshalb schon an einem einzigen Kommentar/
Foto/Status-Event, einer Zeiterfassung oder einem Kundenportal-Zugang mit
einer generischen IntegrityError, praktisch bei jedem echten Datensatz mit
Aktivitaet. Diese vier Tabellen sind reine Anhaengsel ohne eigene
Papierkorb-Sichtbarkeit -- sie sollen mit ihrem Elternobjekt verschwinden,
genau wie rechnung_positionen/eingangsrechnung_positionen das bereits tun.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KASKADEN = (
    ("vorgang_events", "fk_vorgang_events_vorgang_id_vorgaenge", "vorgang_id", "vorgaenge"),
    (
        "highlights",
        "fk_highlights_vorgang_event_id_vorgang_events",
        "vorgang_event_id",
        "vorgang_events",
    ),
    ("zeiterfassung", "fk_zeiterfassung_vorgang_id_vorgaenge", "vorgang_id", "vorgaenge"),
    (
        "kundenportal_zugaenge",
        "fk_kundenportal_zugaenge_kunde_id_kunden",
        "kunde_id",
        "kunden",
    ),
)


def upgrade() -> None:
    for tabelle, fk_name, spalte, referenziert in _KASKADEN:
        op.drop_constraint(fk_name, tabelle, type_="foreignkey")
        op.create_foreign_key(
            fk_name, tabelle, referenziert, [spalte], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    for tabelle, fk_name, spalte, referenziert in reversed(_KASKADEN):
        op.drop_constraint(fk_name, tabelle, type_="foreignkey")
        op.create_foreign_key(fk_name, tabelle, referenziert, [spalte], ["id"])
