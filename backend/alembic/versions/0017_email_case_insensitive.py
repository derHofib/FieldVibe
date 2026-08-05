"""E-Mail-Adressen sind fuer Login-Zwecke case-insensitiv -- bestehende
Datensaetze in users und kundenportal_zugaenge werden auf Kleinschreibung
normalisiert, damit sie zu neu angelegten (bereits app-seitig normalisierten,
siehe app/schemas/user.py und app/schemas/kundenportal.py) Accounts passen.
Kein Schema-Wechsel noetig: die bestehenden Unique-Constraints (uq_users_email
etc.) bleiben gueltig, solange ausnahmslos klein geschrieben gespeichert wird.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email != lower(email)")
    op.execute(
        "UPDATE kundenportal_zugaenge SET email = lower(email) WHERE email != lower(email)"
    )


def downgrade() -> None:
    # Lossy per Definition (die urspruengliche Groß-/Kleinschreibung ist
    # nicht mehr rekonstruierbar) -- absichtlich ein No-Op, da das
    # Kleinschreiben selbst keine Funktionalitaet einschraenkt.
    pass
