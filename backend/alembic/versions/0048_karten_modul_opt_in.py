"""Neues Modul "karten" (Kartenansicht/Mapbox, siehe app/services/
geocoding_service.py) -- anders als jedes andere Modul in MANDANT_MODULE
bewusst opt-IN statt opt-out, weil eine aktivierte Kartenansicht laufende
Mapbox-Kosten verursacht. Kein Schema-Wechsel: deaktivierte_module ist
bereits ein JSONB-Array (siehe 0001_initial_schema). Nur bestehende Zeilen
werden auf "karten" deaktiviert nachgezogen -- der Python-seitige Default in
app/models/mandant.py sorgt ab jetzt dafuer, dass neu angelegte Mandanten
von Anfang an denselben Stand haben.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE mandanten SET deaktivierte_module = deaktivierte_module || '[\"karten\"]'::jsonb "
        "WHERE NOT deaktivierte_module @> '[\"karten\"]'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE mandanten SET deaktivierte_module = deaktivierte_module - 'karten'"
    )
