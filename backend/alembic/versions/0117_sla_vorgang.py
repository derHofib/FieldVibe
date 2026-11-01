"""SLA am Vorgang (docs/konzepte/SLA.md, Phase 3): Snapshot der Richtlinie,
Fristen und Messwerte.

Die Fristen werden beim Anlegen bzw. bei Prioritaets-/Statuswechseln einmal
berechnet und gespeichert; spaetere Aenderungen der Richtlinie wirken nicht
rueckwirkend. sla_laeuft_seit = NULL bedeutet: Uhr steht (wartet_kunde) oder
Vorgang ist erledigt. sla_*_verbraucht_min summiert die Geschaeftsminuten
frueherer Laufabschnitte.

Revision ID: 0117
Revises: 0116
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0117"
down_revision: Union[str, None] = "0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SPALTEN = (
    ("sla_start_am", sa.TIMESTAMP(timezone=True)),
    ("sla_laeuft_seit", sa.TIMESTAMP(timezone=True)),
    ("sla_reaktion_faellig_am", sa.TIMESTAMP(timezone=True)),
    ("sla_loesung_faellig_am", sa.TIMESTAMP(timezone=True)),
    ("sla_reagiert_am", sa.TIMESTAMP(timezone=True)),
    ("sla_geloest_am", sa.TIMESTAMP(timezone=True)),
    ("sla_reaktion_ergebnis", sa.Text()),
    ("sla_loesung_ergebnis", sa.Text()),
)


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.add_column(
        "vorgaenge",
        sa.Column(
            "sla_richtlinie_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sla_richtlinien.id", name="fk_vorgaenge_sla_richtlinie_id"), nullable=True,
        ),
    )
    for name, typ in _SPALTEN:
        op.add_column("vorgaenge", sa.Column(name, typ, nullable=True))
    op.add_column("vorgaenge", sa.Column("sla_reaktion_verbraucht_min", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("vorgaenge", sa.Column("sla_loesung_verbraucht_min", sa.Integer(), nullable=False, server_default="0"))
    for art in ("reaktion", "loesung"):
        op.create_check_constraint(
            f"ck_vorgaenge_sla_{art}_ergebnis_valid", "vorgaenge",
            f"sla_{art}_ergebnis IS NULL OR sla_{art}_ergebnis IN ('erfuellt', 'verletzt')",
        )
    # Der Worker (Phase 4) sucht nur laufende, noch nicht erledigte Fristen.
    op.create_index(
        "ix_vorgaenge_sla_reaktion_offen", "vorgaenge", ["sla_reaktion_faellig_am"],
        postgresql_where=sa.text("sla_laeuft_seit IS NOT NULL AND sla_reagiert_am IS NULL AND geloescht_am IS NULL"),
    )
    op.create_index(
        "ix_vorgaenge_sla_loesung_offen", "vorgaenge", ["sla_loesung_faellig_am"],
        postgresql_where=sa.text("sla_laeuft_seit IS NOT NULL AND sla_geloest_am IS NULL AND geloescht_am IS NULL"),
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")
    op.drop_index("ix_vorgaenge_sla_loesung_offen", table_name="vorgaenge")
    op.drop_index("ix_vorgaenge_sla_reaktion_offen", table_name="vorgaenge")
    for art in ("reaktion", "loesung"):
        op.drop_constraint(f"ck_vorgaenge_sla_{art}_ergebnis_valid", "vorgaenge", type_="check")
    op.drop_column("vorgaenge", "sla_loesung_verbraucht_min")
    op.drop_column("vorgaenge", "sla_reaktion_verbraucht_min")
    for name, _ in reversed(_SPALTEN):
        op.drop_column("vorgaenge", name)
    op.drop_column("vorgaenge", "sla_richtlinie_id")
