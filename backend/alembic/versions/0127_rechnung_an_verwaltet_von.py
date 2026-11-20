"""Abweichender Rechnungsempfaenger, "verwaltet von", Kontakt am Telefonat (Etappe C).

- auftraege/projekte.rechnung_an_kunde_id: Rechnungen gehen an diesen Kunden statt an den Auftraggeber
  (z. B. WEG, die von der Hausverwaltung verwaltet wird).
- kunden.verwaltet_von_kunde_id: WEG "verwaltet von" HV; filtert die Auswahl "Rechnung an".
- telefonate.vor_ort_kontakt_id: Anrufe von Mietern/Hausmeistern zuordnen.

Kein Backfill: alles ist neu und nullable.

Revision ID: 0127
Revises: 0126
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0127"
down_revision: Union[str, None] = "0126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for tabelle in ("auftraege", "projekte"):
        op.add_column(tabelle, sa.Column("rechnung_an_kunde_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{tabelle}_rechnung_an_kunde_id_kunden", tabelle, "kunden", ["rechnung_an_kunde_id"], ["id"]
        )

    op.add_column("kunden", sa.Column("verwaltet_von_kunde_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_kunden_verwaltet_von_kunde_id_kunden", "kunden", "kunden", ["verwaltet_von_kunde_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_kunden_verwaltet_von_nicht_selbst", "kunden", "verwaltet_von_kunde_id <> id"
    )
    op.create_index("ix_kunden_verwaltet_von_kunde_id", "kunden", ["verwaltet_von_kunde_id"])

    op.add_column("telefonate", sa.Column("vor_ort_kontakt_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_telefonate_vor_ort_kontakt_id_vor_ort_kontakte",
        "telefonate",
        "vor_ort_kontakte",
        ["vor_ort_kontakt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_telefonate_vor_ort_kontakt_id", "telefonate", ["vor_ort_kontakt_id"])


def downgrade() -> None:
    op.drop_index("ix_telefonate_vor_ort_kontakt_id", table_name="telefonate")
    op.drop_constraint("fk_telefonate_vor_ort_kontakt_id_vor_ort_kontakte", "telefonate", type_="foreignkey")
    op.drop_column("telefonate", "vor_ort_kontakt_id")

    op.drop_index("ix_kunden_verwaltet_von_kunde_id", table_name="kunden")
    op.drop_constraint("ck_kunden_verwaltet_von_nicht_selbst", "kunden", type_="check")
    op.drop_constraint("fk_kunden_verwaltet_von_kunde_id_kunden", "kunden", type_="foreignkey")
    op.drop_column("kunden", "verwaltet_von_kunde_id")

    for tabelle in ("projekte", "auftraege"):
        op.drop_constraint(f"fk_{tabelle}_rechnung_an_kunde_id_kunden", tabelle, type_="foreignkey")
        op.drop_column(tabelle, "rechnung_an_kunde_id")
