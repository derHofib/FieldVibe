"""Angebot: Auftrag aus Annahme und Nachfassen.

auftrag_vorgang_id verweist auf den Vorgang, der aus der Annahme hervorgeht:
ein neu angelegter oder -- bei einem Angebot, das schon an einem Vorgang
haengt -- der bestehende. Der Mangel-Pfad (Reparatur-Vorgang) setzt ihn nicht,
dort laeuft die Verknuepfung weiter ueber mangel.reparatur_vorgang_id.

nachgefasst_am merkt sich, dass der Worker fuer ein unbeantwortetes Angebot
schon erinnert hat -- damit es genau eine Erinnerung gibt, kein neuer Status.

Beide Spalten sind nullable, kein Backfill: Altbestand hat keinen Auftrag aus
Annahme und wurde nie nachgefasst. Die Tabelle hat bereits Mandanten-RLS samt
Trigger; neue Spalten brauchen keine eigene Policy.

Revision ID: 0107
Revises: 0106
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0107"
down_revision: Union[str, None] = "0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = "fk_angebote_auftrag_vorgang_id_vorgaenge"


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column("angebote", sa.Column("auftrag_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(_FK, "angebote", "vorgaenge", ["auftrag_vorgang_id"], ["id"])
    op.add_column("angebote", sa.Column("nachgefasst_am", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_column("angebote", "nachgefasst_am")
    op.drop_constraint(_FK, "angebote", type_="foreignkey")
    op.drop_column("angebote", "auftrag_vorgang_id")
