"""Partner.ansprechpartner von einem einzelnen Freitext-Namen auf dieselbe
JSONB-Liste wie Kunde.ansprechpartner umgestellt -- mehrere Kontakte pro
Partner mit Kategorisierung (operativ/Eskalationsstufe), siehe
app/schemas/kontakt.py. Bestehende einzeilige Werte werden als ein Eintrag
mit diesem Namen uebernommen, damit keine Daten verloren gehen.

Revision ID: 0069
Revises: 0068
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0069"
down_revision: Union[str, None] = "0068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE partner
        ALTER COLUMN ansprechpartner TYPE jsonb
        USING (
          CASE
            WHEN ansprechpartner IS NULL OR btrim(ansprechpartner) = '' THEN '[]'::jsonb
            ELSE jsonb_build_array(
              jsonb_build_object(
                'id', gen_random_uuid(),
                'name', ansprechpartner,
                'position', NULL,
                'telefon', NULL,
                'email', NULL,
                'operativ', false,
                'eskalationsstufe', NULL,
                'notiz', NULL
              )
            )
          END
        )
        """
    )
    op.execute("ALTER TABLE partner ALTER COLUMN ansprechpartner SET DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE partner ALTER COLUMN ansprechpartner SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE partner ALTER COLUMN ansprechpartner DROP NOT NULL")
    op.execute("ALTER TABLE partner ALTER COLUMN ansprechpartner DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE partner
        ALTER COLUMN ansprechpartner TYPE text
        USING (ansprechpartner->0->>'name')
        """
    )
