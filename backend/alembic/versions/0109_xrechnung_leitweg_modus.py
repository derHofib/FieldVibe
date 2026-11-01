"""XRechnung: Leitweg-ID und Format am Kunden, Schnappschuss am Beleg; E-Rechnung-Modus.

kunden.leitweg_id ist die Routing-Kennung oeffentlicher Auftraggeber (BT-10
"Buyer reference" in der XRechnung); kunden.e_rechnung_format waehlt das
Profil ('zugferd' = EN 16931, 'xrechnung'), NULL = Automatik (Leitweg-ID
gesetzt -> xrechnung, sonst zugferd).

rechnungen.leitweg_id und rechnungen.e_rechnung_profil ('en16931' |
'xrechnung') halten fest, was beim Versand tatsaechlich in der E-Rechnung
stand (GoBD: spaetere Aenderungen am Kunden duerfen den versendeten Beleg
nicht umdeuten). Beide bleiben NULL bei Entwuerfen und Belegen ohne E-Rechnung.

Datenmigration: mandanten.firmendaten bekommt e_rechnung_modus. Mandanten mit
e_rechnung_aktiv=true behalten ihr Verhalten ('alle'), alle anderen 'aus';
e_rechnung_aktiv bleibt als abgeleiteter Wert erhalten. Die Tabellen haben
bereits Mandanten-RLS samt Trigger, neue Spalten brauchen keine eigene Policy.

Revision ID: 0109
Revises: 0108
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0109"
down_revision: Union[str, None] = "0108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kurznamen: die Namenskonvention (ck_<Tabelle>_<Name>) ergaenzt das Praefix.
_CK_FORMAT = "e_rechnung_format_valid"
_CK_PROFIL = "e_rechnung_profil_valid"


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column("kunden", sa.Column("leitweg_id", sa.Text(), nullable=True))
    op.add_column("kunden", sa.Column("e_rechnung_format", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CK_FORMAT, "kunden", "e_rechnung_format IS NULL OR e_rechnung_format IN ('zugferd', 'xrechnung')"
    )
    op.add_column("rechnungen", sa.Column("leitweg_id", sa.Text(), nullable=True))
    op.add_column("rechnungen", sa.Column("e_rechnung_profil", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CK_PROFIL, "rechnungen", "e_rechnung_profil IS NULL OR e_rechnung_profil IN ('en16931', 'xrechnung')"
    )

    op.execute(
        """
        UPDATE mandanten
        SET firmendaten = firmendaten || jsonb_build_object(
            'e_rechnung_modus',
            CASE WHEN firmendaten->>'e_rechnung_aktiv' = 'true' THEN 'alle' ELSE 'aus' END
        )
        WHERE NOT jsonb_exists(firmendaten, 'e_rechnung_modus')
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.execute("UPDATE mandanten SET firmendaten = firmendaten - 'e_rechnung_modus'")
    op.drop_constraint(_CK_PROFIL, "rechnungen", type_="check")
    op.drop_column("rechnungen", "e_rechnung_profil")
    op.drop_column("rechnungen", "leitweg_id")
    op.drop_constraint(_CK_FORMAT, "kunden", type_="check")
    op.drop_column("kunden", "e_rechnung_format")
    op.drop_column("kunden", "leitweg_id")
