"""Kundenportal B2C: Annahmenachweis (angebot_annahmen) und Widerruf.

angebot_annahmen haelt je Annahme/Ablehnung/Widerruf im Portal, wer (Zugang +
E-Mail/Name als Momentaufnahme), wann, von welcher IP/mit welchem User-Agent
und welche Fassung (SHA-256 ueber die kanonische Serialisierung des Angebots,
siehe angebot_service.fassung_sha256) entschieden hat; bei Verbrauchern
zusaetzlich die angezeigte Widerrufsbelehrung. Die Tabelle ist append-only:
die Policy gilt wie bei allen Mandantentabellen, ein Trigger verbietet UPDATE
und DELETE auch dem Tabellenbesitzer und super_admin -- die Eintraege sind
Beweismittel. TRUNCATE bleibt bewusst moeglich (Test-Cleanup, Mandanten-
Totalloeschung); die FK auf angebote verhindert nur das endgueltige Loeschen
eines Angebots mit Nachweis.

angebote.widerrufen_am und der neue Status 'widerrufen' bilden den Widerruf
nach § 356a BGB ab. Bestehende Zeilen bleiben unveraendert, kein Backfill.

Mandanten, die portal_verbraucherschutz nie gesetzt haben, behalten ihr
bisheriges Verhalten (Fallback "aus" im Code) -- es gibt hier absichtlich
keinen Daten-Update auf firmendaten.

Downgrade ist verlustbehaftet: die Nachweise gehen mit der Tabelle verloren,
widerrufene Angebote werden wieder 'angenommen'.

Revision ID: 0111
Revises: 0110
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0111"
down_revision: Union[str, None] = "0110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_NEU = ("entwurf", "versendet", "angenommen", "abgelehnt", "widerrufen")
_STATUS_ALT = ("entwurf", "versendet", "angenommen", "abgelehnt")
_AKTIONEN = ("annahme", "ablehnung", "widerruf")
_TRIGGER_FUNKTION = "angebot_annahmen_append_only"


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.add_column("angebote", sa.Column("widerrufen_am", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f("ck_angebote_status_valid"), "angebote", type_="check")
    op.create_check_constraint(op.f("ck_angebote_status_valid"), "angebote", f"status IN {_STATUS_NEU}")

    op.create_table(
        "angebot_annahmen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("angebot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("kunden_portal_zugang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("zugang_email", sa.Text(), nullable=False),
        sa.Column("zugang_name", sa.Text(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("fassung_sha256", sa.Text(), nullable=False),
        sa.Column("b2c_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("belehrung_version", sa.Text(), nullable=True),
        sa.Column("belehrung_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_angebot_annahmen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["angebot_id"], ["angebote.id"], name="fk_angebot_annahmen_angebot_id_angebote"),
        sa.ForeignKeyConstraint(
            ["kunden_portal_zugang_id"],
            ["kundenportal_zugaenge.id"],
            name="fk_angebot_annahmen_zugang_kundenportal_zugaenge",
        ),
        sa.CheckConstraint(f"aktion IN {_AKTIONEN}", name=op.f("ck_angebot_annahmen_aktion_valid")),
        sa.CheckConstraint("char_length(fassung_sha256) = 64", name=op.f("ck_angebot_annahmen_fassung_sha256_laenge")),
    )
    op.create_index("ix_angebot_annahmen_angebot_id_created_at", "angebot_annahmen", ["angebot_id", "created_at"])
    op.create_index("ix_angebot_annahmen_mandant_id", "angebot_annahmen", ["mandant_id"])

    op.execute("ALTER TABLE angebot_annahmen ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE angebot_annahmen FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON angebot_annahmen
        USING (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER_FUNKTION}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'angebot_annahmen ist append-only (% nicht erlaubt)', TG_OP
            USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_angebot_annahmen_append_only
        BEFORE UPDATE OR DELETE ON angebot_annahmen
        FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNKTION}()
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.execute("DROP TRIGGER IF EXISTS trg_angebot_annahmen_append_only ON angebot_annahmen")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNKTION}()")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON angebot_annahmen")
    op.drop_table("angebot_annahmen")

    op.execute("UPDATE angebote SET status = 'angenommen' WHERE status = 'widerrufen'")
    op.drop_constraint(op.f("ck_angebote_status_valid"), "angebote", type_="check")
    op.create_check_constraint(op.f("ck_angebote_status_valid"), "angebote", f"status IN {_STATUS_ALT}")
    op.drop_column("angebote", "widerrufen_am")
