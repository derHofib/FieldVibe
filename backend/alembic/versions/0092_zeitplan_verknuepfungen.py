"""Zeitplan-Verknuepfungen: Schritt <-> Fremdgewerk (Partner), Meilenstein <->
Materiallieferung (Bestellung mit Liefertermin).

vorgang_id existiert bereits auf projekt_aufgaben (Phase 1) und wird fuer
verknuepfte Schritte mitgenutzt. SET NULL, damit ein hart geloeschter Partner
bzw. eine hart geloeschte Bestellung den Zeitplan nicht blockiert -- weich
geloeschte (Papierkorb) Bestellungen filtert die Anwendung.

Revision ID: 0092
Revises: 0091
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0092"
down_revision: Union[str, None] = "0091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bestellungen", sa.Column("liefertermin", sa.Date(), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("bestellung_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projekt_aufgaben_bestellung_id_bestellungen",
        "projekt_aufgaben",
        "bestellungen",
        ["bestellung_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projekt_aufgaben_partner_id_partner",
        "projekt_aufgaben",
        "partner",
        ["partner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_projekt_aufgaben_bestellung_id", "projekt_aufgaben", ["bestellung_id"])
    op.create_index("ix_projekt_aufgaben_partner_id", "projekt_aufgaben", ["partner_id"])


def downgrade() -> None:
    op.drop_index("ix_projekt_aufgaben_partner_id", table_name="projekt_aufgaben")
    op.drop_index("ix_projekt_aufgaben_bestellung_id", table_name="projekt_aufgaben")
    op.drop_constraint("fk_projekt_aufgaben_partner_id_partner", "projekt_aufgaben", type_="foreignkey")
    op.drop_constraint("fk_projekt_aufgaben_bestellung_id_bestellungen", "projekt_aufgaben", type_="foreignkey")
    op.drop_column("projekt_aufgaben", "partner_id")
    op.drop_column("projekt_aufgaben", "bestellung_id")
    op.drop_column("bestellungen", "liefertermin")
