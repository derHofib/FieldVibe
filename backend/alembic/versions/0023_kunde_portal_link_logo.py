"""Verschiebt den personalisierten Kundenportal-Login-Link von einzelnen
KundenportalZugaenge (pro Ansprechpartner) auf den Kunden selbst -- ein
Link pro Kunde, den jeder Mitarbeiter des Kunden mit einem eigenen
KundenportalZugang nutzen kann (Passwort-Eingabe bleibt weiterhin Pflicht).
Ausserdem: optionales Firmenlogo je Kunde fuer eine personalisierte
Portal-Login-Seite.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kunden", sa.Column("portal_slug", sa.Text(), nullable=True))
    op.execute(
        "UPDATE kunden SET portal_slug = replace(gen_random_uuid()::text, '-', '') "
        "WHERE portal_slug IS NULL"
    )
    op.alter_column("kunden", "portal_slug", nullable=False)
    op.create_unique_constraint(op.f("uq_kunden_portal_slug"), "kunden", ["portal_slug"])

    op.add_column("kunden", sa.Column("logo_object_key", sa.Text(), nullable=True))

    op.drop_constraint(
        "uq_kundenportal_zugaenge_login_slug", "kundenportal_zugaenge", type_="unique"
    )
    op.drop_column("kundenportal_zugaenge", "login_slug")


def downgrade() -> None:
    op.add_column("kundenportal_zugaenge", sa.Column("login_slug", sa.Text(), nullable=True))
    op.execute(
        "UPDATE kundenportal_zugaenge SET login_slug = replace(gen_random_uuid()::text, '-', '') "
        "WHERE login_slug IS NULL"
    )
    op.alter_column("kundenportal_zugaenge", "login_slug", nullable=False)
    op.create_unique_constraint(
        "uq_kundenportal_zugaenge_login_slug", "kundenportal_zugaenge", ["login_slug"]
    )

    op.drop_column("kunden", "logo_object_key")
    op.drop_constraint(op.f("uq_kunden_portal_slug"), "kunden", type_="unique")
    op.drop_column("kunden", "portal_slug")
