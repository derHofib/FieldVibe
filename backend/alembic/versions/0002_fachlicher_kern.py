"""Phase 2: Kunden, Anlagen, Vertraege, Vorgaenge, Vorgang-Events, Tags + RLS

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = ("kunden", "anlagen", "vertraege", "vorgaenge", "vorgang_events", "tags", "tag_assignments")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
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
    )


def upgrade() -> None:
    # --- kunden -----------------------------------------------------------
    op.create_table(
        "kunden",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kundennummer", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("typ", sa.Text(), nullable=True),
        sa.Column("ansprechpartner", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("adresse", postgresql.JSONB(), nullable=True),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_kunden_mandant_id_mandanten"),
        sa.UniqueConstraint("mandant_id", "kundennummer", name="uq_kunden_mandant_kundennummer"),
        sa.CheckConstraint(
            "typ IS NULL OR typ IN ('privat','gewerbe','oeffentlich','hausverwaltung')",
            name="ck_kunden_typ_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_kunden_updated_at BEFORE UPDATE ON kunden "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_kunden_mandant_id", "kunden", ["mandant_id"])

    # --- anlagen ------------------------------------------------------------
    op.create_table(
        "anlagen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("adresse", postgresql.JSONB(), nullable=False),
        sa.Column("anlagentyp", sa.Text(), nullable=True),
        sa.Column("qr_code", sa.Text(), nullable=True),
        sa.Column("stammdaten", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("geo_lat", sa.Float(), nullable=True),
        sa.Column("geo_lng", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_anlagen_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_anlagen_kunde_id_kunden"),
        sa.UniqueConstraint("qr_code", name="uq_anlagen_qr_code"),
    )
    op.execute(
        "CREATE TRIGGER trg_anlagen_updated_at BEFORE UPDATE ON anlagen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_anlagen_mandant_id", "anlagen", ["mandant_id"])
    op.create_index("ix_anlagen_kunde_id", "anlagen", ["kunde_id"])

    # --- vertraege ----------------------------------------------------------
    op.create_table(
        "vertraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("abrechnungsart", sa.Text(), nullable=False),
        sa.Column("konditionen", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("laufzeit_von", sa.Date(), nullable=True),
        sa.Column("laufzeit_bis", sa.Date(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vertraege_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_vertraege_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_vertraege_anlage_id_anlagen"),
        sa.CheckConstraint(
            "abrechnungsart IN ('pauschale','aufwand','festpreis','wartungsvertrag')",
            name="ck_vertraege_abrechnungsart_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_vertraege_updated_at BEFORE UPDATE ON vertraege "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_vertraege_mandant_id", "vertraege", ["mandant_id"])
    op.create_index("ix_vertraege_kunde_id", "vertraege", ["kunde_id"])

    # --- vorgaenge ------------------------------------------------------------
    op.create_table(
        "vorgaenge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgangsnummer", sa.Text(), nullable=False),
        sa.Column("kunde_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anlage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vertrag_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_vorgang_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("abrechnungsart", sa.Text(), nullable=False),
        sa.Column("leistungstyp", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="neu"),
        sa.Column("prioritaet", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("abgeschlossen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vorgaenge_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["kunde_id"], ["kunden.id"], name="fk_vorgaenge_kunde_id_kunden"),
        sa.ForeignKeyConstraint(["anlage_id"], ["anlagen.id"], name="fk_vorgaenge_anlage_id_anlagen"),
        sa.ForeignKeyConstraint(["vertrag_id"], ["vertraege.id"], name="fk_vorgaenge_vertrag_id_vertraege"),
        sa.ForeignKeyConstraint(["parent_vorgang_id"], ["vorgaenge.id"], name="fk_vorgaenge_parent_vorgang_id_vorgaenge"),
        sa.UniqueConstraint("mandant_id", "vorgangsnummer", name="uq_vorgaenge_mandant_vorgangsnummer"),
        sa.CheckConstraint(
            "abrechnungsart IN ('pauschale','aufwand','festpreis','wartungsvertrag','gewaehrleistung')",
            name="ck_vorgaenge_abrechnungsart_valid",
        ),
        sa.CheckConstraint(
            "leistungstyp IN ('installation','pruefung','wartung','stoerung','beratung','planung')",
            name="ck_vorgaenge_leistungstyp_valid",
        ),
        sa.CheckConstraint(
            "status IN ('neu','geplant','in_arbeit','wartet_kunde','abgeschlossen','abgerechnet','storniert')",
            name="ck_vorgaenge_status_valid",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_vorgaenge_updated_at BEFORE UPDATE ON vorgaenge "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("idx_vorgaenge_feed", "vorgaenge", ["mandant_id", sa.text("last_activity_at DESC"), sa.text("id DESC")])
    op.create_index("ix_vorgaenge_kunde_id", "vorgaenge", ["kunde_id"])
    op.create_index("ix_vorgaenge_anlage_id", "vorgaenge", ["anlage_id"])

    # --- vorgang_events (append-only event stream / chat) --------------------
    op.create_table(
        "vorgang_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgang_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kundensichtbar", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ref_entity_type", sa.Text(), nullable=True),
        sa.Column("ref_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_vorgang_events_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["vorgang_id"], ["vorgaenge.id"], name="fk_vorgang_events_vorgang_id_vorgaenge"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], name="fk_vorgang_events_author_user_id_users"),
        sa.UniqueConstraint("client_uuid", name="uq_vorgang_events_client_uuid"),
        sa.CheckConstraint(
            "event_type IN ('kommentar','status_change','foto','dokument','mangel',"
            "'angebot','material','zeit_start','zeit_stop','termin','rechnung_status','system')",
            name="ck_vorgang_events_event_type_valid",
        ),
    )
    op.create_index("idx_events_vorgang", "vorgang_events", ["vorgang_id", sa.text("id DESC")])
    op.create_index("ix_vorgang_events_mandant_id", "vorgang_events", ["mandant_id"])

    # Append-only stream drives the feed ordering: every new event bumps the
    # parent Vorgang's last_activity_at. Runs as the inserting session's own
    # role, so it stays subject to that session's RLS -- fine, since a
    # Vorgang and its Events always share the same mandant_id by construction.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION touch_vorgang_last_activity() RETURNS trigger AS $$
        BEGIN
          UPDATE vorgaenge SET last_activity_at = now() WHERE id = NEW.vorgang_id;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_vorgang_events_touch_activity AFTER INSERT ON vorgang_events "
        "FOR EACH ROW EXECUTE FUNCTION touch_vorgang_last_activity()"
    )

    # --- tags / tag_assignments ----------------------------------------------
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("farbe", sa.Text(), nullable=True),
        sa.Column("system_tag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_tags_mandant_id_mandanten"),
        sa.UniqueConstraint("mandant_id", "label", name="uq_tags_mandant_label"),
    )
    op.execute(
        "CREATE TRIGGER trg_tags_updated_at BEFORE UPDATE ON tags "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_tags_mandant_id", "tags", ["mandant_id"])

    op.create_table(
        "tag_assignments",
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Text(), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name="fk_tag_assignments_tag_id_tags", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_tag_assignments_mandant_id_mandanten"),
        sa.CheckConstraint(
            "entity_type IN ('kunde','anlage','vorgang')", name="ck_tag_assignments_entity_type_valid"
        ),
    )
    op.create_index("ix_tag_assignments_entity", "tag_assignments", ["entity_type", "entity_id"])
    op.create_index("ix_tag_assignments_mandant_id", "tag_assignments", ["mandant_id"])

    for table in TENANT_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS mandant_isolation ON {table}")

    op.drop_table("tag_assignments")
    op.drop_table("tags")
    op.execute("DROP TRIGGER IF EXISTS trg_vorgang_events_touch_activity ON vorgang_events")
    op.execute("DROP FUNCTION IF EXISTS touch_vorgang_last_activity()")
    op.drop_table("vorgang_events")
    op.drop_table("vorgaenge")
    op.drop_table("vertraege")
    op.drop_table("anlagen")
    op.drop_table("kunden")
