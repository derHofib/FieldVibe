"""Zeitplan Phase 3: Basisplaene (Soll/Ist-Snapshots) und Projektvorlagen.

Basisplan-Eintraege haengen per CASCADE am Element -- ein geloeschtes Element
verschwindet aus dem Vergleich. Vorlagen sind mandantenweit und referenzieren
ihre Elemente nur ueber die lokale `ref` (kein FK auf projekt_aufgaben), damit
sie vom Quellprojekt unabhaengig bleiben.

Revision ID: 0093
Revises: 0092
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0093"
down_revision: Union[str, None] = "0092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLEN = (
    "projekt_basisplaene",
    "projekt_basisplan_eintraege",
    "projekt_vorlagen",
    "projekt_vorlage_elemente",
    "projekt_vorlage_abhaengigkeiten",
)


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


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _mandant_spalte(tabelle: str) -> tuple[sa.Column, sa.ForeignKeyConstraint]:
    return (
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name=f"fk_{tabelle}_mandant_id_mandanten"),
    )


def upgrade() -> None:
    m, m_fk = _mandant_spalte("projekt_basisplaene")
    op.create_table(
        "projekt_basisplaene",
        _uuid_pk(),
        m,
        sa.Column("projekt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        m_fk,
        sa.ForeignKeyConstraint(
            ["projekt_id"], ["projekte.id"], name="fk_projekt_basisplaene_projekt_id_projekte", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_projekt_basisplaene_erstellt_von_users"),
    )
    op.create_index("ix_projekt_basisplaene_mandant_id", "projekt_basisplaene", ["mandant_id"])
    op.create_index("ix_projekt_basisplaene_projekt_id", "projekt_basisplaene", ["projekt_id"])

    m, m_fk = _mandant_spalte("projekt_basisplan_eintraege")
    op.create_table(
        "projekt_basisplan_eintraege",
        _uuid_pk(),
        m,
        sa.Column("basisplan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_am", sa.Date(), nullable=False),
        sa.Column("ende_am", sa.Date(), nullable=False),
        m_fk,
        sa.ForeignKeyConstraint(
            ["basisplan_id"],
            ["projekt_basisplaene.id"],
            name="fk_projekt_basisplan_eintraege_basisplan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["projekt_aufgaben.id"],
            name="fk_projekt_basisplan_eintraege_element_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("basisplan_id", "element_id", name="uq_projekt_basisplan_eintrag"),
    )
    op.create_index("ix_projekt_basisplan_eintraege_mandant_id", "projekt_basisplan_eintraege", ["mandant_id"])
    op.create_index("ix_projekt_basisplan_eintraege_basisplan_id", "projekt_basisplan_eintraege", ["basisplan_id"])
    op.create_index("ix_projekt_basisplan_eintraege_element_id", "projekt_basisplan_eintraege", ["element_id"])

    m, m_fk = _mandant_spalte("projekt_vorlagen")
    op.create_table(
        "projekt_vorlagen",
        _uuid_pk(),
        m,
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        m_fk,
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_projekt_vorlagen_erstellt_von_users"),
    )
    op.execute(
        "CREATE TRIGGER trg_projekt_vorlagen_updated_at BEFORE UPDATE ON projekt_vorlagen "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("ix_projekt_vorlagen_mandant_id", "projekt_vorlagen", ["mandant_id"])

    m, m_fk = _mandant_spalte("projekt_vorlage_elemente")
    op.create_table(
        "projekt_vorlage_elemente",
        _uuid_pk(),
        m,
        sa.Column("vorlage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("phase_ref", sa.Text(), nullable=True),
        sa.Column("offset_tage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dauer_tage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        m_fk,
        sa.ForeignKeyConstraint(
            ["vorlage_id"], ["projekt_vorlagen.id"], name="fk_projekt_vorlage_elemente_vorlage_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("vorlage_id", "ref", name="uq_projekt_vorlage_element_ref"),
        sa.CheckConstraint(
            "typ IN ('phase', 'schritt', 'meilenstein')", name="ck_projekt_vorlage_element_typ_valid"
        ),
        sa.CheckConstraint("dauer_tage >= 1", name="ck_projekt_vorlage_element_dauer_valid"),
    )
    op.create_index("ix_projekt_vorlage_elemente_mandant_id", "projekt_vorlage_elemente", ["mandant_id"])
    op.create_index("ix_projekt_vorlage_elemente_vorlage_id", "projekt_vorlage_elemente", ["vorlage_id"])

    m, m_fk = _mandant_spalte("projekt_vorlage_abhaengigkeiten")
    op.create_table(
        "projekt_vorlage_abhaengigkeiten",
        _uuid_pk(),
        m,
        sa.Column("vorlage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vorgaenger_ref", sa.Text(), nullable=False),
        sa.Column("nachfolger_ref", sa.Text(), nullable=False),
        sa.Column("art", sa.Text(), nullable=False, server_default="ende_anfang"),
        sa.Column("versatz_tage", sa.Integer(), nullable=False, server_default="0"),
        m_fk,
        sa.ForeignKeyConstraint(
            ["vorlage_id"],
            ["projekt_vorlagen.id"],
            name="fk_projekt_vorlage_abhaengigkeiten_vorlage_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("vorlage_id", "vorgaenger_ref", "nachfolger_ref", name="uq_projekt_vorlage_abh_paar"),
        sa.CheckConstraint(
            "art IN ('ende_anfang', 'anfang_anfang', 'ende_ende')", name="ck_projekt_vorlage_abh_art_valid"
        ),
    )
    op.create_index("ix_projekt_vorlage_abhaengigkeiten_mandant_id", "projekt_vorlage_abhaengigkeiten", ["mandant_id"])
    op.create_index("ix_projekt_vorlage_abhaengigkeiten_vorlage_id", "projekt_vorlage_abhaengigkeiten", ["vorlage_id"])

    for tabelle in _TABELLEN:
        _enable_rls(tabelle)


def downgrade() -> None:
    for tabelle in reversed(_TABELLEN):
        op.execute(f"DROP POLICY IF EXISTS mandant_isolation ON {tabelle}")
        if tabelle == "projekt_vorlagen":
            op.execute("DROP TRIGGER IF EXISTS trg_projekt_vorlagen_updated_at ON projekt_vorlagen")
        op.drop_table(tabelle)
