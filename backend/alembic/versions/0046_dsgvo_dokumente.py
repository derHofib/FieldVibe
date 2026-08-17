"""Plattformweite DSGVO-Compliance-Dokumente (AVV-Vorlage, Datenschutz-
erklaerung, Impressum, Loeschkonzept, TOM-Dokument, Meldeprozess,
Verzeichnis von Verarbeitungstaetigkeiten) -- Upload/Verwaltung im
Super-Admin-Bereich, siehe app/api/routes/dsgvo.py. Bewusst nicht
mandantengebunden (Betreiber-Compliance, keine fachlichen Kundendaten),
daher keine RLS-Policy wie bei den Mandanten-Tabellen.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DSGVO_DOKUMENT_TYPEN = (
    "avv_vorlage",
    "datenschutzerklaerung",
    "impressum",
    "loeschkonzept",
    "tom_dokument",
    "meldeprozess",
    "verzeichnis_verarbeitungstaetigkeiten",
)


def upgrade() -> None:
    op.create_table(
        "dsgvo_dokumente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("typ", sa.Text(), nullable=False, unique=True),
        sa.Column("dateiname", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("groesse_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "hochgeladen_von",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(f"typ IN {DSGVO_DOKUMENT_TYPEN}", name="ck_dsgvo_dokumente_typ_valid"),
    )


def downgrade() -> None:
    op.drop_table("dsgvo_dokumente")
