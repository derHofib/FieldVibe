"""Neuer Rechte-Bereich "partner" in der Account-Typen-Matrix.

Die Partner-/Nachunternehmer-Routen (app/api/routes/partner.py) pruefen
bisher per require_roles() direkt auf die Rollen-Literale "disponent"/
"techniker" -- die es seit der Rechte-Matrix/account_typ-Umstellung (siehe
Migration 0037) als tatsaechlichen User.role-Wert nicht mehr gibt (jeder
Mitarbeiter-Account laeuft ueber role="custom" + account_typ_id). Der
Bereich war dadurch fuer keinen account_typ-basierten Mitarbeiter erreichbar,
unabhaengig von seinen tatsaechlich vergebenen Rechten. Analog zu Migration
0052 ("formulare" nachtraeglich ergaenzt) wird hier "partner" als eigener
Rechte-Bereich ergaenzt, den ein mandant_admin einem Account-Typ frei
zuweisen kann.

Revision ID: 0070
Revises: 0069
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0070"
down_revision: Union[str, None] = "0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung', 'formulare', 'partner'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute("DELETE FROM account_typ_rechte WHERE bereich = 'partner'")
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        "CHECK (bereich IN ('vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', "
        "'statistik', 'mitarbeiterverwaltung', 'formulare'))"
    )
