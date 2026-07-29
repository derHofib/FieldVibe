"""Phase 3: notifications, Volltextsuche (tsvector) und pg_trgm-Indizes

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration backfills search_vector across every tenant's existing
    # rows. The alembic connection carries no app.current_mandant /
    # app.is_super_admin session vars, so without this the RLS policies
    # (FORCE ROW LEVEL SECURITY, same as every other tenant table) would
    # make the UPDATE below silently match zero rows -- it would not error,
    # it would just leave every existing row's search_vector NULL.
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    # --- notifications ---------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("ref_entity_type", sa.Text(), nullable=True),
        sa.Column("ref_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gelesen_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_notifications_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_notifications_user_id_users"),
    )
    op.create_index("ix_notifications_mandant_id", "notifications", ["mandant_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id", sa.text("id DESC")])

    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON notifications
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

    # --- Volltextsuche: materialisierte tsvector-Spalte auf vorgaenge -----
    # Deckt Titel, Beschreibung UND alle Kommentar-Event-Texte ab (Abschnitt
    # 5.3). Titel/Beschreibung werden per Trigger bei jedem UPDATE neu
    # gesetzt; jedes neue Event haengt seinen Text zusaetzlich an (siehe
    # zweiter Trigger unten) statt das Ganze neu zu berechnen.
    op.add_column("vorgaenge", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.execute(
        """
        UPDATE vorgaenge SET search_vector =
          to_tsvector('german', coalesce(titel, '') || ' ' || coalesce(beschreibung, ''))
        """
    )
    op.alter_column("vorgaenge", "search_vector", nullable=False)
    op.create_index(
        "ix_vorgaenge_search_vector", "vorgaenge", ["search_vector"], postgresql_using="gin"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_vorgang_search_vector() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('german', coalesce(NEW.titel, '') || ' ' || coalesce(NEW.beschreibung, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_vorgaenge_search_vector BEFORE INSERT OR UPDATE OF titel, beschreibung "
        "ON vorgaenge FOR EACH ROW EXECUTE FUNCTION set_vorgang_search_vector()"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION append_vorgang_event_search_vector() RETURNS trigger AS $$
        BEGIN
          IF NEW.body IS NOT NULL THEN
            UPDATE vorgaenge
            SET search_vector = search_vector || to_tsvector('german', NEW.body)
            WHERE id = NEW.vorgang_id;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_vorgang_events_search_vector AFTER INSERT ON vorgang_events "
        "FOR EACH ROW EXECUTE FUNCTION append_vorgang_event_search_vector()"
    )

    # --- pg_trgm Typeahead-Indizes -----------------------------------------
    op.execute("CREATE INDEX ix_kunden_name_trgm ON kunden USING gin (name gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_kunden_kundennummer_trgm ON kunden USING gin (kundennummer gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_anlagen_bezeichnung_trgm ON anlagen USING gin (bezeichnung gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_vorgaenge_vorgangsnummer_trgm ON vorgaenge USING gin (vorgangsnummer gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_tags_label_trgm ON tags USING gin (label gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tags_label_trgm")
    op.execute("DROP INDEX IF EXISTS ix_vorgaenge_vorgangsnummer_trgm")
    op.execute("DROP INDEX IF EXISTS ix_anlagen_bezeichnung_trgm")
    op.execute("DROP INDEX IF EXISTS ix_kunden_kundennummer_trgm")
    op.execute("DROP INDEX IF EXISTS ix_kunden_name_trgm")

    op.execute("DROP TRIGGER IF EXISTS trg_vorgang_events_search_vector ON vorgang_events")
    op.execute("DROP FUNCTION IF EXISTS append_vorgang_event_search_vector()")
    op.execute("DROP TRIGGER IF EXISTS trg_vorgaenge_search_vector ON vorgaenge")
    op.execute("DROP FUNCTION IF EXISTS set_vorgang_search_vector()")
    op.drop_index("ix_vorgaenge_search_vector", table_name="vorgaenge")
    op.drop_column("vorgaenge", "search_vector")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON notifications")
    op.drop_table("notifications")
