"""Phase 6: maengel, angebote, angebot_positionen, rechnungen (Geschaeftsprozesse)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANGEL_SCHWEREGRADE = ("kritisch", "hoch", "mittel", "niedrig")
MANGEL_STATUS = ("offen", "in_angebot", "in_bearbeitung", "behoben", "abgelehnt")
ANGEBOT_STATUS = ("entwurf", "versendet", "angenommen", "abgelehnt")
RECHNUNG_STATUS = ("entwurf", "versendet", "bezahlt", "storniert")


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
    # --- angebote (vor maengel, wegen FK maengel.angebot_id) ------------
    op.create_table(
        "angebote",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("angebotsnummer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="entwurf"),
        sa.Column("mwst_satz", sa.Numeric(5, 2), nullable=False, server_default="19.00"),
        sa.Column("gueltig_bis", sa.Date(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("versendet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("angenommen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("abgelehnt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_angebote_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_angebote_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_angebote_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_angebote_erstellt_von_users"),
        sa.UniqueConstraint("mandant_id", "angebotsnummer", name="uq_angebote_mandant_angebotsnummer"),
        sa.CheckConstraint(f"status IN {ANGEBOT_STATUS}", name="ck_angebote_status_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_angebote_updated_at BEFORE UPDATE ON angebote "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_angebote_mandant_id", "angebote", ["mandant_id"])
    op.create_index("ix_angebote_kunde_id", "angebote", ["kunde_id"])
    op.execute("ALTER TABLE angebote ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE angebote FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("angebote"))

    # --- angebot_positionen ----------------------------------------------
    op.create_table(
        "angebot_positionen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("angebot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("menge", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("einheit", sa.Text(), nullable=False, server_default="Stk"),
        sa.Column("einzelpreis", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_angebot_positionen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(
            ["angebot_id"], ["angebote.id"], name="fk_angebot_positionen_angebot_id_angebote", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_angebot_positionen_angebot_id", "angebot_positionen", ["angebot_id"])
    op.execute("ALTER TABLE angebot_positionen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE angebot_positionen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("angebot_positionen"))

    # --- maengel ------------------------------------------------------------
    op.create_table(
        "maengel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("beschreibung", sa.Text(), nullable=False),
        sa.Column("schweregrad", sa.Text(), nullable=False, server_default="mittel"),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("gemeldet_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("angebot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reparatur_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("behoben_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_maengel_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_maengel_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_maengel_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(["gemeldet_von"], ["users.id"], name="fk_maengel_gemeldet_von_users"),
        sa.ForeignKeyConstraint(["angebot_id"], ["angebote.id"], name="fk_maengel_angebot_id_angebote"),
        sa.ForeignKeyConstraint(
            ["reparatur_vorgang_id"], ["vorgaenge.id"], name="fk_maengel_reparatur_vorgang_id_vorgaenge"
        ),
        sa.CheckConstraint(f"schweregrad IN {MANGEL_SCHWEREGRADE}", name="ck_maengel_schweregrad_valid"),
        sa.CheckConstraint(f"status IN {MANGEL_STATUS}", name="ck_maengel_status_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_maengel_updated_at BEFORE UPDATE ON maengel "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_maengel_mandant_id", "maengel", ["mandant_id"])
    op.create_index("ix_maengel_vorgang_id", "maengel", ["vorgang_id"])
    op.execute("ALTER TABLE maengel ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE maengel FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("maengel"))

    # --- rechnungen ----------------------------------------------------
    op.create_table(
        "rechnungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rechnungsnummer", sa.Text(), nullable=False),
        sa.Column("betrag_netto", sa.Numeric(10, 2), nullable=False),
        sa.Column("mwst_satz", sa.Numeric(5, 2), nullable=False, server_default="19.00"),
        sa.Column("status", sa.Text(), nullable=False, server_default="entwurf"),
        sa.Column("faellig_am", sa.Date(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("versendet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("bezahlt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_rechnungen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_rechnungen_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_rechnungen_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_rechnungen_erstellt_von_users"),
        sa.UniqueConstraint("mandant_id", "rechnungsnummer", name="uq_rechnungen_mandant_rechnungsnummer"),
        sa.CheckConstraint(f"status IN {RECHNUNG_STATUS}", name="ck_rechnungen_status_valid"),
    )
    op.execute(
        "CREATE TRIGGER trg_rechnungen_updated_at BEFORE UPDATE ON rechnungen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_rechnungen_mandant_id", "rechnungen", ["mandant_id"])
    op.create_index("ix_rechnungen_kunde_id", "rechnungen", ["kunde_id"])
    op.execute("ALTER TABLE rechnungen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rechnungen FORCE ROW LEVEL SECURITY")
    op.execute(_mandant_isolation_policy("rechnungen"))


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON rechnungen")
    op.drop_table("rechnungen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON maengel")
    op.drop_table("maengel")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON angebot_positionen")
    op.drop_table("angebot_positionen")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON angebote")
    op.drop_table("angebote")
