"""Debitorenbuchhaltung: Zahlungseingaenge (rechnung_zahlungen) + neuer
Status "teilweise_bezahlt".

Spiegelt die bereits vorhandene Kreditorenseite (0044_kreditorenbuchhaltung.py,
eingangsrechnung_zahlungen) -- dort gibt es Teilzahlungen und einen offenen
Betrag laengst, auf der Ausgangsseite fehlten sie komplett. bezahlt_am war
bisher immer "jetzt" (siehe app/api/routes/rechnungen.py), ein Kontoauszug
von letzter Woche liess sich nicht rueckdatiert buchen.

Reihenfolge ist hier bewusst: Tabelle anlegen -> Indizes -> Backfill-INSERT
-> RLS aktivieren. FORCE ROW LEVEL SECURITY gilt auch fuer den Tabellen-
Owner; in der Migration ist app.current_mandant ungesetzt, WITH CHECK wuerde
also jeden INSERT nach RLS-Aktivierung still verwerfen. Der Backfill muss
deshalb VOR der RLS-Policy laufen.

Backfill: jede bestehende Rechnung mit status='bezahlt' hat noch keinen
Zahlungssatz -- ohne Nachtrag waere ihr offener Betrag == Brutto und sie
wuerde faelschlich als offen erscheinen (OP-Liste, Uebersicht-Filter). Der
Betrag wird identisch zu rechnung_service.netto_betrag() ermittelt:
Positionssumme gewinnt, sonst betrag_netto.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_NEU = ("entwurf", "versendet", "teilweise_bezahlt", "bezahlt", "storniert")
_STATUS_ALT = ("entwurf", "versendet", "bezahlt", "storniert")
_ZAHLUNGSARTEN = ("ueberweisung", "bar", "karte", "lastschrift", "sonstiges")


def _mandant_isolation_policy(table: str) -> str:
    return f"""
        CREATE POLICY mandant_isolation ON {table}
        USING (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """


def upgrade() -> None:
    op.create_table(
        "rechnung_zahlungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rechnung_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("betrag", sa.Numeric(10, 2), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("zahlungsart", sa.Text(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("storniert_zahlung_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_rechnung_zahlungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["rechnung_id"], ["rechnungen.id"], name="fk_rechnung_zahlungen_rechnung_id_rechnungen", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["storniert_zahlung_id"], ["rechnung_zahlungen.id"],
            name="fk_rechnung_zahlungen_storniert_zahlung_id_rechnung_zahlungen",
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_rechnung_zahlungen_erstellt_von_users"),
        sa.CheckConstraint("betrag <> 0", name="ck_rechnung_zahlungen_betrag_nicht_null"),
        sa.CheckConstraint(
            f"zahlungsart IS NULL OR zahlungsart IN {_ZAHLUNGSARTEN}",
            name="ck_rechnung_zahlungen_zahlungsart_valid",
        ),
    )
    op.create_index("ix_rechnung_zahlungen_rechnung_id", "rechnung_zahlungen", ["rechnung_id"])
    op.create_index("ix_rechnung_zahlungen_mandant_id_datum", "rechnung_zahlungen", ["mandant_id", "datum"])

    # Backfill VOR RLS-Aktivierung, siehe Modul-Docstring.
    op.execute(
        """
        INSERT INTO rechnung_zahlungen (mandant_id, rechnung_id, betrag, datum, erstellt_von, notiz)
        SELECT
            r.mandant_id,
            r.id,
            round(b.netto * (1 + r.mwst_satz / 100), 2),
            coalesce(r.bezahlt_am::date, r.versendet_am::date, r.created_at::date),
            r.erstellt_von,
            'Backfill Migration 0056: Altbestand ohne Einzelzahlungen'
        FROM rechnungen r
        CROSS JOIN LATERAL (
            SELECT coalesce(
                (SELECT sum(p.menge * p.einzelpreis) FROM rechnung_positionen p WHERE p.rechnung_id = r.id),
                r.betrag_netto
            ) AS netto
        ) b
        WHERE r.status = 'bezahlt' AND b.netto <> 0
        """
    )

    op.execute("ALTER TABLE rechnung_zahlungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rechnung_zahlungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("rechnung_zahlungen"))

    op.drop_constraint(op.f("ck_rechnungen_status_valid"), "rechnungen", type_="check")
    op.create_check_constraint(
        op.f("ck_rechnungen_status_valid"), "rechnungen", f"status IN {_STATUS_NEU}"
    )

    # GoBD-Luecke schliessen: faellig_am/leistungsdatum waren bisher auch
    # nach dem Versand per PATCH aenderbar, obwohl beide im archivierten PDF
    # stehen und leistungsdatum Pflichtangabe nach Paragraph 14 Abs. 4 Nr. 6
    # UStG ist. Rein applikatorische Sperre in rechnungen.py, hier keine
    # Schema-Aenderung noetig.


def downgrade() -> None:
    op.execute("UPDATE rechnungen SET status = 'versendet' WHERE status = 'teilweise_bezahlt'")
    op.drop_constraint(op.f("ck_rechnungen_status_valid"), "rechnungen", type_="check")
    op.create_check_constraint(
        op.f("ck_rechnungen_status_valid"), "rechnungen", f"status IN {_STATUS_ALT}"
    )

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON rechnung_zahlungen")
    op.drop_table("rechnung_zahlungen")
