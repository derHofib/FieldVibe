"""Abrechnung: km-Anteil getrennt sperren, eigener Fahrzeit-Satz.

Eine Zeitbuchung kann Stunden UND km tragen. Bisher sperrte die erste
uebernommene Position (zeit/fahrzeit/leistung ODER fahrtkosten) die ganze
Zeile -- der jeweils andere Anteil tauchte danach nie mehr als offen auf.
Jetzt sperrt der Stunden-Anteil weiter ueber buchungsstatus/
abgerechnet_rechnung_id, der km-Anteil ueber die neue Spalte
km_abgerechnet_rechnung_id (Quelle "fahrtkosten").

mandanten.fahrzeit_satz_netto: eigener Stundensatz fuer "fahrzeit"-
Vorschlaege (bisher immer Preis 0).

Revision ID: 0097
Revises: 0096
Create Date: 2026-10-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0097"
down_revision: Union[str, None] = "0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AKTIONEN_ALT = (
    "'angelegt', 'geaendert', 'geloescht', 'wiederhergestellt', 'vorgemerkt', "
    "'vormerkung_zurueckgezogen', 'gebucht', 'buchung_storniert', 'abgerechnet', "
    "'abrechnung_zurueckgesetzt'"
)
_AKTIONEN_NEU = _AKTIONEN_ALT + ", 'km_abgerechnet', 'km_abrechnung_zurueckgesetzt'"

# Stunden-Position derselben Rechnung/desselben Vorgangs fuer diese Zeile --
# spiegelt rechnung_service._zeiterfassung_quelle_filter: "zeit" = Auftrags-
# zeile ohne LV-Kopplung, "fahrzeit" = Fahrzeit-Zeile, "leistung" =
# Auftragszeile mit genau dieser LV-Position.
_HAT_STUNDEN_POSITION = """
    EXISTS (
        SELECT 1 FROM rechnung_positionen p
        JOIN rechnungen r ON r.id = p.rechnung_id
        WHERE p.rechnung_id = z.abgerechnet_rechnung_id
          AND COALESCE(p.vorgang_id, r.vorgang_id) = z.vorgang_id
          AND (
            (p.quelle = 'zeit' AND z.kategorie = 'auftrag' AND z.lv_position_id IS NULL)
            OR (p.quelle = 'fahrzeit' AND z.kategorie = 'fahrzeit')
            OR (p.quelle = 'leistung' AND z.kategorie = 'auftrag'
                AND z.lv_position_id IS NOT NULL AND p.lv_position_id = z.lv_position_id)
          )
    )
"""


def upgrade() -> None:
    # RLS ist FORCE: ohne Super-Admin-Flag sieht das Backfill-UPDATE keine Zeile.
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.add_column(
        "zeiterfassung",
        sa.Column("km_abgerechnet_rechnung_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_zeiterfassung_km_abgerechnet_rechnung_id_rechnungen",
        "zeiterfassung",
        "rechnungen",
        ["km_abgerechnet_rechnung_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_zeiterfassung_km_abgerechnet_rechnung_id",
        "zeiterfassung",
        ["km_abgerechnet_rechnung_id"],
    )

    op.add_column("mandanten", sa.Column("fahrzeit_satz_netto", sa.Numeric(8, 2), nullable=True))
    op.create_check_constraint(
        "fahrzeit_satz_netto_nicht_negativ",
        "mandanten",
        "fahrzeit_satz_netto IS NULL OR fahrzeit_satz_netto >= 0",
    )

    op.drop_constraint("aktion_valid", "zeiterfassung_aenderungen", type_="check")
    op.create_check_constraint(
        "aktion_valid", "zeiterfassung_aenderungen", f"aktion IN ({_AKTIONEN_NEU})"
    )

    # Backfill (datenerhaltend). Alt-Zustand: eine abgerechnete Zeile mit km
    # zeigt ueber abgerechnet_rechnung_id auf Rechnung R, egal ob R den
    # Stunden- oder den km-Anteil (oder beide) uebernommen hat.
    #
    # Regel 1: hat R eine "fahrtkosten"-Position fuer den Vorgang der Zeile
    # (Position.vorgang_id, sonst Rechnung.vorgang_id -- Altpositionen vor
    # 0087), war der km-Anteil dort abgerechnet -> km_abgerechnet_rechnung_id = R.
    # Regel 2: hat R fuer genau diese Zeile KEINE Stunden-Position, war die
    # Zeile nur wegen der fahrtkosten-Position gesperrt -> Stunden wieder offen
    # (buchungsstatus 'gebucht', abgerechnet_rechnung_id NULL).
    # Zeilen ohne passende fahrtkosten-Position bleiben unveraendert; ihr km-
    # Anteil gilt ab jetzt als offen (genau das behebt den Fehler).
    # Das Aenderungsprotokoll wird bewusst nicht nachgetragen.
    op.execute(
        f"""
        UPDATE zeiterfassung z
        SET km_abgerechnet_rechnung_id = z.abgerechnet_rechnung_id,
            buchungsstatus = CASE WHEN {_HAT_STUNDEN_POSITION} THEN z.buchungsstatus ELSE 'gebucht' END,
            abgerechnet_rechnung_id = CASE WHEN {_HAT_STUNDEN_POSITION} THEN z.abgerechnet_rechnung_id ELSE NULL END
        WHERE z.km IS NOT NULL
          AND z.kategorie IN ('auftrag', 'fahrzeit')
          AND z.buchungsstatus = 'abgerechnet'
          AND z.abgerechnet_rechnung_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM rechnung_positionen p
            JOIN rechnungen r ON r.id = p.rechnung_id
            WHERE p.rechnung_id = z.abgerechnet_rechnung_id
              AND p.quelle = 'fahrtkosten'
              AND COALESCE(p.vorgang_id, r.vorgang_id) = z.vorgang_id
          )
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    # Zurueck zur Kopplung: ein gesperrter km-Anteil sperrt die ganze Zeile.
    # Nur wo kein Stunden-Verweis besteht (sonst bleibt dieser) und die
    # Rechnung nicht als freigegebener Entwurf im Papierkorb liegt (dort
    # galt der Verweis als frei).
    op.execute(
        """
        UPDATE zeiterfassung z
        SET abgerechnet_rechnung_id = z.km_abgerechnet_rechnung_id, buchungsstatus = 'abgerechnet'
        WHERE z.km_abgerechnet_rechnung_id IS NOT NULL
          AND z.abgerechnet_rechnung_id IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM rechnungen r
            WHERE r.id = z.km_abgerechnet_rechnung_id
              AND r.status = 'entwurf' AND r.geloescht_am IS NOT NULL
          )
        """
    )

    # Protokollzeilen der neuen Aktionen auf die Alt-Aktionen abbilden, sonst
    # verletzen sie die alte CHECK-Constraint.
    op.execute(
        "UPDATE zeiterfassung_aenderungen SET aktion = 'abgerechnet' WHERE aktion = 'km_abgerechnet'"
    )
    op.execute(
        "UPDATE zeiterfassung_aenderungen SET aktion = 'abrechnung_zurueckgesetzt' "
        "WHERE aktion = 'km_abrechnung_zurueckgesetzt'"
    )
    op.drop_constraint("aktion_valid", "zeiterfassung_aenderungen", type_="check")
    op.create_check_constraint(
        "aktion_valid", "zeiterfassung_aenderungen", f"aktion IN ({_AKTIONEN_ALT})"
    )

    op.drop_constraint("fahrzeit_satz_netto_nicht_negativ", "mandanten", type_="check")
    op.drop_column("mandanten", "fahrzeit_satz_netto")

    op.drop_index("ix_zeiterfassung_km_abgerechnet_rechnung_id", table_name="zeiterfassung")
    op.drop_constraint(
        "fk_zeiterfassung_km_abgerechnet_rechnung_id_rechnungen", "zeiterfassung", type_="foreignkey"
    )
    op.drop_column("zeiterfassung", "km_abgerechnet_rechnung_id")
