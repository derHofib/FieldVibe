"""Verknuepfung Projekt > Auftrag > Vorgang (Konzept auftrag-projekt).

- vorgaenge: verknuepfung_eigenstaendig (+ _am/_von) -- "Eigenstaendig fuehren":
  Zuordnung bleibt eingefroren und wird Nutzern ohne Recht ausgeblendet.
- vorgang_events: neue Ereignistypen zuordnung_geaendert, eigenstaendig_gesetzt,
  eigenstaendig_aufgehoben (Check-Constraint erweitert).
- Datenbereinigung: Vorgang mit Auftrag bekommt das Projekt des Auftrags
  ("Projekt des Auftrags gewinnt"); die betroffene Anzahl wird ins Log geschrieben.

Keine neue Tabelle, die bestehenden RLS-Policies/Trigger sind nicht
spaltenspezifisch und gelten unveraendert.

Downgrade: Spalten weg, Constraint zurueck (Ereignisse der neuen Typen werden
geloescht, wie in 0052). Die Datenbereinigung wird bewusst NICHT rueckgaengig
gemacht: das alte Projekt ist nach dem UPDATE nirgends mehr gespeichert, und
der bereinigte Zustand ist auch fuer den alten Code der gueltige.

Revision ID: 0118
Revises: 0117
Create Date: 2026-11-18
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0118"
down_revision: Union[str, None] = "0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

_ALTE_EVENT_TYPEN = (
    "kommentar", "status_change", "foto", "dokument", "mangel", "angebot", "material",
    "zeit_start", "zeit_stop", "termin", "rechnung_status", "system", "unterschrift",
    "eingangsrechnung_status", "formular", "leistung",
)
_NEUE_EVENT_TYPEN = _ALTE_EVENT_TYPEN + (
    "zuordnung_geaendert",
    "eigenstaendig_gesetzt",
    "eigenstaendig_aufgehoben",
)


def _constraint_setzen(typen: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE vorgang_events DROP CONSTRAINT ck_vorgang_events_event_type_valid")
    op.execute(
        "ALTER TABLE vorgang_events ADD CONSTRAINT ck_vorgang_events_event_type_valid "
        f"CHECK (event_type IN {typen})"
    )


def upgrade() -> None:
    op.add_column(
        "vorgaenge",
        sa.Column("verknuepfung_eigenstaendig", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "vorgaenge", sa.Column("verknuepfung_eigenstaendig_am", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "vorgaenge",
        sa.Column(
            "verknuepfung_eigenstaendig_von",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name=op.f("fk_vorgaenge_verknuepfung_eigenstaendig_von_users")),
            nullable=True,
        ),
    )
    _constraint_setzen(_NEUE_EVENT_TYPEN)

    # Seit 0117 greift app.is_super_admin nicht mehr; die Migrationsrolle
    # unterliegt als Tabelleneigentuemerin wegen FORCE ROW LEVEL SECURITY den
    # Policies und wuerde ohne app.current_mandant stillschweigend 0 Zeilen
    # sehen. FORCE daher fuer die Dauer der (transaktionalen) Bereinigung
    # abschalten -- schlaegt laut fehl, falls die Rolle nicht Eigentuemerin ist.
    op.execute("ALTER TABLE vorgaenge NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auftraege NO FORCE ROW LEVEL SECURITY")
    try:
        bind = op.get_bind()
        betroffen = bind.execute(
            sa.text(
                "SELECT count(*) FROM vorgaenge v JOIN auftraege a ON v.auftrag_id = a.id "
                "WHERE v.projekt_id IS DISTINCT FROM a.projekt_id"
            )
        ).scalar_one()
        log.info("0118: %s Vorgaenge bekommen das Projekt ihres Auftrags", betroffen)
        print(f"[0118] Datenbereinigung: {betroffen} Vorgang/Vorgaenge erhalten das Projekt ihres Auftrags")
        if betroffen:
            bind.execute(
                sa.text(
                    "UPDATE vorgaenge v SET projekt_id = a.projekt_id FROM auftraege a "
                    "WHERE v.auftrag_id = a.id AND v.projekt_id IS DISTINCT FROM a.projekt_id"
                )
            )
    finally:
        op.execute("ALTER TABLE vorgaenge FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE auftraege FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Siehe upgrade: ohne FORCE-Abschaltung saehe das DELETE keine Zeilen und
    # das Wiederanlegen des Constraints scheiterte an den neuen Typen.
    op.execute("ALTER TABLE vorgang_events NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM vorgang_events WHERE event_type IN "
        "('zuordnung_geaendert', 'eigenstaendig_gesetzt', 'eigenstaendig_aufgehoben')"
    )
    op.execute("ALTER TABLE vorgang_events FORCE ROW LEVEL SECURITY")
    _constraint_setzen(_ALTE_EVENT_TYPEN)
    op.drop_column("vorgaenge", "verknuepfung_eigenstaendig_von")
    op.drop_column("vorgaenge", "verknuepfung_eigenstaendig_am")
    op.drop_column("vorgaenge", "verknuepfung_eigenstaendig")
