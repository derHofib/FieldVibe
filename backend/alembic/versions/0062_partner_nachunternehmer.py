"""Nachunternehmer-Verwaltung: partner (Stammdaten, mandantengebunden wie
Kunde), partner_nachweise (Freistellungsbescheinigung/Haftpflicht/
Gewerbeanmeldung/etc. mit Ablaufdatum -- dasselbe Ablauf-Ueberwachungsmuster
wie pruefmittel.naechste_kalibrierung_am, nur ohne eigenen Scheduler-Job in
dieser Runde) und partner_zugaenge (Partnerportal-Login, spiegelt
kundenportal_zugaenge exakt).

vorgaenge bekommt vier neue, alle nullable Spalten fuer die Delegation an
einen Partner: partner_id, partner_freigabe_status (Partner muss aktiv
annehmen/ablehnen -- bewusst kein stilles Auto-Zuweisen, siehe
app/services/partner_service.py), partner_ablehnung_grund,
partner_honorar_netto (die mit dem Partner vereinbarte Verguetung, komplett
getrennt von dem, was der Endkunde zahlt -- Partner sieht nie Angebots-/
Rechnungsbetraege des Kunden, siehe app/api/routes/partner_portal.py).

"nachunternehmer" wird als neuer Schluessel in MANDANT_MODULE ergaenzt
(app/models/mandant.py) -- opt-out wie jedes andere Modul.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    # --- partner -----------------------------------------------------------
    op.create_table(
        "partner",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("gewerk", sa.Text(), nullable=True),
        sa.Column("ansprechpartner", sa.Text(), nullable=True),
        sa.Column("telefon", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("adresse", postgresql.JSONB(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_partner_mandant_id_mandanten"),
    )
    op.execute(
        "CREATE TRIGGER trg_partner_updated_at BEFORE UPDATE ON partner "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_partner_mandant_id", "partner", ["mandant_id"])
    op.execute("ALTER TABLE partner ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("partner"))

    # --- partner_nachweise ---------------------------------------------------
    op.create_table(
        "partner_nachweise",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("gueltig_bis", sa.Date(), nullable=True),
        sa.Column("dokument_s3_key", sa.Text(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_partner_nachweise_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner.id"], name="fk_partner_nachweise_partner_id_partner", ondelete="CASCADE"),
        sa.CheckConstraint(
            "typ IN ('freistellungsbescheinigung','haftpflichtversicherung','gewerbeanmeldung',"
            "'handwerksrolle','avv_dsgvo','sonstiges')",
            name="ck_partner_nachweise_typ_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_partner_nachweise_updated_at BEFORE UPDATE ON partner_nachweise "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_partner_nachweise_mandant_id", "partner_nachweise", ["mandant_id"])
    op.create_index("ix_partner_nachweise_partner_id", "partner_nachweise", ["partner_id"])
    op.execute("ALTER TABLE partner_nachweise ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_nachweise FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("partner_nachweise"))

    # --- partner_zugaenge (Partnerportal-Login) -----------------------------
    op.create_table(
        "partner_zugaenge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_partner_zugaenge_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner.id"], name="fk_partner_zugaenge_partner_id_partner", ondelete="CASCADE"),
        sa.UniqueConstraint("email", name="uq_partner_zugaenge_email"),
    )
    op.execute(
        "CREATE TRIGGER trg_partner_zugaenge_updated_at BEFORE UPDATE ON partner_zugaenge "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_partner_zugaenge_mandant_id", "partner_zugaenge", ["mandant_id"])
    op.create_index("ix_partner_zugaenge_partner_id", "partner_zugaenge", ["partner_id"])
    op.execute("ALTER TABLE partner_zugaenge ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_zugaenge FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("partner_zugaenge"))

    # --- vorgaenge: Delegation an einen Partner -----------------------------
    op.add_column("vorgaenge", sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("vorgaenge", sa.Column("partner_freigabe_status", sa.Text(), nullable=True))
    op.add_column("vorgaenge", sa.Column("partner_ablehnung_grund", sa.Text(), nullable=True))
    op.add_column("vorgaenge", sa.Column("partner_honorar_netto", sa.Numeric(10, 2), nullable=True))
    op.create_foreign_key(
        "fk_vorgaenge_partner_id_partner", "vorgaenge", "partner", ["partner_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_vorgaenge_partner_freigabe_status_valid",
        "vorgaenge",
        "partner_freigabe_status IS NULL OR partner_freigabe_status IN "
        "('vorgeschlagen','angenommen','abgelehnt')",
    )
    op.create_index("ix_vorgaenge_partner_id", "vorgaenge", ["partner_id"])


def downgrade() -> None:
    op.drop_index("ix_vorgaenge_partner_id", table_name="vorgaenge")
    op.drop_constraint("ck_vorgaenge_partner_freigabe_status_valid", "vorgaenge", type_="check")
    op.drop_constraint("fk_vorgaenge_partner_id_partner", "vorgaenge", type_="foreignkey")
    op.drop_column("vorgaenge", "partner_honorar_netto")
    op.drop_column("vorgaenge", "partner_ablehnung_grund")
    op.drop_column("vorgaenge", "partner_freigabe_status")
    op.drop_column("vorgaenge", "partner_id")

    op.drop_table("partner_zugaenge")
    op.drop_table("partner_nachweise")
    op.drop_table("partner")
