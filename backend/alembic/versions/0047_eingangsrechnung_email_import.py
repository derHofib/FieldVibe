"""Eingangsrechnung: E-Mail-Import-Entwurf (Rechnungseingang-Postfach)

Fuehrt den Status "entwurf" ein (automatisch per IMAP-Import angelegt, siehe
app/services/email_ingest_service.py, MandantIntegration typ="imap") sowie
zwei Metadatenspalten fuer die Herkunft-Mail. erstellt_von wird nullable,
weil ein per E-Mail importierter Entwurf noch von keinem Mitarbeiter erfasst
wurde -- NULL heisst hier "System-Import", nicht "unbekannt".

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EINGANGSRECHNUNG_STATUS = ("entwurf", "offen", "bezahlt", "storniert")


# Migration 0043 hat den Constraint-Namen als nackten String statt via
# op.f() vergeben -- SQLAlchemy wendet die "ck"-Namenskonvention
# (app/db/base.py) dadurch auf den bereits fertigen Namen nochmal an und
# verdoppelt ihn (vgl. Migration 0030 vs. 0036 fuer material_bedarfe, wo
# op.f() von Anfang an verwendet wurde und keine Verdopplung auftrat). Der
# tatsaechliche Name in der DB ist deshalb
# "ck_eingangsrechnungen_ck_eingangsrechnungen_status_valid". Um hier nicht
# noch eine weitere Verdopplungsstufe zu riskieren, wird der Constraint per
# rohem SQL (nicht ueber op.create_check_constraint/op.f()) ab-, bzw.
# angelegt -- das umgeht die Namenskonvention komplett.
_ALTER_NAME = "ck_eingangsrechnungen_ck_eingangsrechnungen_status_valid"


def upgrade() -> None:
    op.add_column("eingangsrechnungen", sa.Column("email_absender", sa.Text(), nullable=True))
    op.add_column("eingangsrechnungen", sa.Column("email_betreff", sa.Text(), nullable=True))
    op.alter_column("eingangsrechnungen", "erstellt_von", nullable=True)

    op.execute(f"ALTER TABLE eingangsrechnungen DROP CONSTRAINT {_ALTER_NAME}")
    op.execute(
        f"ALTER TABLE eingangsrechnungen ADD CONSTRAINT {_ALTER_NAME} "
        f"CHECK (status IN {EINGANGSRECHNUNG_STATUS})"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE eingangsrechnungen DROP CONSTRAINT {_ALTER_NAME}")
    op.execute(
        f"ALTER TABLE eingangsrechnungen ADD CONSTRAINT {_ALTER_NAME} "
        "CHECK (status IN ('offen', 'bezahlt', 'storniert'))"
    )

    op.alter_column("eingangsrechnungen", "erstellt_von", nullable=False)
    op.drop_column("eingangsrechnungen", "email_betreff")
    op.drop_column("eingangsrechnungen", "email_absender")
