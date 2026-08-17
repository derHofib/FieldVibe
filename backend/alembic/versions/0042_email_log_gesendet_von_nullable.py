"""email_log.gesendet_von wird nullable -- fuer automatisch vom Mahnwesen-
Scheduler versendete Mahnungen gibt es keinen handelnden Nutzer, analog zum
bestehenden AuditLog.actor_user_id-Muster fuer Scheduler-Laeufe.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("email_log", "gesendet_von", nullable=True)


def downgrade() -> None:
    op.alter_column("email_log", "gesendet_von", nullable=False)
