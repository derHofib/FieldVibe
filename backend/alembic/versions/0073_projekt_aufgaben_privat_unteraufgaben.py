"""Projekt-Aufgaben: private Aufgaben, Unteraufgaben, Direktverknuepfungen.

Drei Erweiterungen von projekt_aufgaben:

1. projekt_id/spalte_id werden nullable -- eine "private Aufgabe" ist
   technisch eine projekt_aufgaben-Zeile ohne Projekt (projekt_id IS NULL),
   dadurch teilt sie sich Modell/Schema/Endpunkte mit den Kanban-Aufgaben
   statt eine zweite Tabelle zu brauchen. ck_projekt_aufgaben_spalte_erfordert_projekt
   stellt sicher, dass spalte_id nur gesetzt sein kann, wenn auch projekt_id
   gesetzt ist (eine private Aufgabe hat keine Spalte).
2. eltern_aufgabe_id (selbstreferenzierend, ON DELETE CASCADE) fuer
   Unteraufgaben, bewusst nur eine Ebene tief -- das Verschachteln von
   Unteraufgaben von Unteraufgaben wird in app/api/routes/projekte.py
   applikationsseitig abgelehnt, nicht per Constraint (waere rekursiv
   aufwendig fuer wenig Nutzen).
3. anlage_id/kunde_id/standort_id (je ON DELETE SET NULL) als direkte,
   rein referenzielle Verknuepfungen -- Schnellzugriff aus einer Aufgabe
   heraus, analog zu vorgang_id, ohne Status-Sync.

erledigt_am (nullable Timestamp) ergaenzt einen Abhak-Status, den es bisher
nur implizit ueber die Kanban-Spalte gab -- fuer private Aufgaben und
Unteraufgaben (die keine eigene Spalte haben) ist das der einzige Weg, sie
als erledigt zu markieren.

Rechte: der Router lockert die Pruefung applikationsseitig (kein Migrations-
Bestandteil) -- private Aufgaben (projekt_id IS NULL) sind fuer jeden
authentifizierten Nutzer nutzbar, unabhaengig vom Rechte-Bereich "projekte",
der weiterhin ausschliesslich die Kanban-Funktion schuetzt.

Revision ID: 0073
Revises: 0072
Create Date: 2026-08-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: Union[str, None] = "0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("projekt_aufgaben", "projekt_id", nullable=True)
    op.alter_column("projekt_aufgaben", "spalte_id", nullable=True)

    op.add_column("projekt_aufgaben", sa.Column("eltern_aufgabe_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("standort_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projekt_aufgaben", sa.Column("erledigt_am", sa.TIMESTAMP(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_projekt_aufgaben_eltern_aufgabe_id_projekt_aufgaben",
        "projekt_aufgaben", "projekt_aufgaben", ["eltern_aufgabe_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_projekt_aufgaben_anlage_id_anlagen",
        "projekt_aufgaben", "anlagen", ["anlage_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projekt_aufgaben_kunde_id_kunden",
        "projekt_aufgaben", "kunden", ["kunde_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projekt_aufgaben_standort_id_standorte",
        "projekt_aufgaben", "standorte", ["standort_id"], ["id"], ondelete="SET NULL",
    )

    op.create_check_constraint(
        "ck_projekt_aufgaben_spalte_erfordert_projekt",
        "projekt_aufgaben",
        "spalte_id IS NULL OR projekt_id IS NOT NULL",
    )

    op.create_index("ix_projekt_aufgaben_eltern_aufgabe_id", "projekt_aufgaben", ["eltern_aufgabe_id"])
    op.create_index("ix_projekt_aufgaben_anlage_id", "projekt_aufgaben", ["anlage_id"])
    op.create_index("ix_projekt_aufgaben_kunde_id", "projekt_aufgaben", ["kunde_id"])
    op.create_index("ix_projekt_aufgaben_standort_id", "projekt_aufgaben", ["standort_id"])


def downgrade() -> None:
    op.drop_index("ix_projekt_aufgaben_standort_id", table_name="projekt_aufgaben")
    op.drop_index("ix_projekt_aufgaben_kunde_id", table_name="projekt_aufgaben")
    op.drop_index("ix_projekt_aufgaben_anlage_id", table_name="projekt_aufgaben")
    op.drop_index("ix_projekt_aufgaben_eltern_aufgabe_id", table_name="projekt_aufgaben")

    op.drop_constraint("ck_projekt_aufgaben_spalte_erfordert_projekt", "projekt_aufgaben", type_="check")

    op.drop_constraint("fk_projekt_aufgaben_standort_id_standorte", "projekt_aufgaben", type_="foreignkey")
    op.drop_constraint("fk_projekt_aufgaben_kunde_id_kunden", "projekt_aufgaben", type_="foreignkey")
    op.drop_constraint("fk_projekt_aufgaben_anlage_id_anlagen", "projekt_aufgaben", type_="foreignkey")
    op.drop_constraint(
        "fk_projekt_aufgaben_eltern_aufgabe_id_projekt_aufgaben", "projekt_aufgaben", type_="foreignkey"
    )

    op.drop_column("projekt_aufgaben", "erledigt_am")
    op.drop_column("projekt_aufgaben", "standort_id")
    op.drop_column("projekt_aufgaben", "kunde_id")
    op.drop_column("projekt_aufgaben", "anlage_id")
    op.drop_column("projekt_aufgaben", "eltern_aufgabe_id")

    op.execute("DELETE FROM projekt_aufgaben WHERE projekt_id IS NULL")
    op.alter_column("projekt_aufgaben", "spalte_id", nullable=False)
    op.alter_column("projekt_aufgaben", "projekt_id", nullable=False)
