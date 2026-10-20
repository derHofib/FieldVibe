"""TOTP-MFA fuer Mitarbeiter-Accounts: Spalten an users.

Reine Spalten, keine neue Tabelle -- RLS-Policies und Trigger der Tabelle users
gelten unveraendert. mfa_secret_enc ist der Fernet-verschluesselte Base32-
Schluessel (app.core.security.encrypt_secret); solange mfa_aktiv false ist,
steht dort ein noch unbestaetigtes Einrichtungs-Secret. mfa_wiederherstellung
haelt nur HMAC-Hashes der Einmalcodes. mfa_letzter_schritt ist der zuletzt
akzeptierte TOTP-Zeitschritt (Replay-Schutz).

Die Mandanteneinstellung mfa_pflicht liegt in mandanten.firmendaten (JSONB)
und braucht keine Migration; fehlt sie, gilt "aus".

Revision ID: 0112
Revises: 0111
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0112"
down_revision: Union[str, None] = "0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_aktiv", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_secret_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_wiederherstellung", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("mfa_letzter_schritt", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("mfa_aktiviert_am", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for spalte in ("mfa_aktiviert_am", "mfa_letzter_schritt", "mfa_wiederherstellung", "mfa_secret_enc", "mfa_aktiv"):
        op.drop_column("users", spalte)
