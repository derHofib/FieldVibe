"""Phase 1: mandanten, users, integrationen, audit_log + Row Level Security

Revision ID: 0001
Revises:
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # --- mandanten ---------------------------------------------------------
    op.create_table(
        "mandanten",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("branche", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="aktiv"),
        sa.Column(
            "branding",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('aktiv','pausiert','gekuendigt')", name="ck_mandanten_status_valid"
        ),
        sa.UniqueConstraint("slug", name="uq_mandanten_slug"),
    )
    op.execute(
        "CREATE TRIGGER trg_mandanten_updated_at BEFORE UPDATE ON mandanten "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # --- users ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_users_mandant_id_mandanten"
        ),
        sa.CheckConstraint(
            "role IN ('super_admin','mandant_admin','disponent','techniker')",
            name="ck_users_role_valid",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.execute(
        "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_users_mandant_id", "users", ["mandant_id"])

    # --- mandant_integrationen ----------------------------------------
    op.create_table(
        "mandant_integrationen",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("secret_ref", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["mandant_id"],
            ["mandanten.id"],
            name="fk_mandant_integrationen_mandant_id_mandanten",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_mandant_integrationen_updated_at "
        "BEFORE UPDATE ON mandant_integrationen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index(
        "ix_mandant_integrationen_mandant_id", "mandant_integrationen", ["mandant_id"]
    )

    # --- audit_log (append-only, no updated_at) -------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandanten.id"], name="fk_audit_log_mandant_id_mandanten"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_log_actor_user_id_users"
        ),
    )
    op.create_index("ix_audit_log_mandant_id", "audit_log", ["mandant_id"])
    op.create_index(
        "ix_audit_log_created_at", "audit_log", ["created_at"], postgresql_using="btree"
    )

    # --- Row Level Security ---------------------------------------------
    # The app DB role owns these tables (it created them), and Postgres
    # exempts table owners from RLS unless it is explicitly forced -- so
    # FORCE is required, not optional, for isolation to actually hold.
    op.execute("ALTER TABLE mandanten ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mandanten FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandant_isolation ON mandanten
        USING (
          id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        WITH CHECK (
          id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
          OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
        )
        """
    )

    for table in ("users", "mandant_integrationen", "audit_log"):
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


def downgrade() -> None:
    for table in ("audit_log", "mandant_integrationen", "users", "mandanten"):
        op.execute(f"DROP POLICY IF EXISTS mandant_isolation ON {table}")

    op.drop_table("audit_log")
    op.drop_table("mandant_integrationen")
    op.drop_table("users")
    op.drop_table("mandanten")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
