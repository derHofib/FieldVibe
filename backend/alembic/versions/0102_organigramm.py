"""Organigramm: Org-Einheiten, Positionen, Besetzungen, Rechte-Overrides, Scopes.

Datenbasis fuer die Rechte-Engine (docs/konzepte/ORGANIGRAMM.md, Schritt 1):
keine Verhaltensaenderung, users.account_typ_id bleibt der Rechtetraeger.
account_typ_rechte bekommt mandant_id (+ eigene RLS) und scope; die DB-Checks
fuer bereich/aktion entfallen (Validierung gegen app/core/rechte_registry.py).
Datenmigration: je Mandant eine Wurzelposition "Geschaeftsfuehrung" (aktive
mandant_admin), je Account-Typ eine Position darunter (aktive custom-Nutzer).

Revision ID: 0102
Revises: 0101
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0102"
down_revision: Union[str, None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPES = "'eigene', 'team', 'teilbaum', 'bereich', 'mandant'"

# Registry-Stand zum Zeitpunkt der Migration (bewusst eingefroren, kein Import):
# Bereiche, die den Scope "eigene" kennen.
_BEREICHE_MIT_EIGENE = "'vorgaenge', 'kunden', 'dispo', 'projekte', 'mitarbeiterverwaltung', 'organigramm'"

# Check-Werte von vor 0100 (fuer den Downgrade).
_BEREICHE_ALT = (
    "'vorgaenge', 'kunden', 'material', 'dispo', 'abrechnung', 'statistik', "
    "'mitarbeiterverwaltung', 'formulare', 'partner', 'projekte', 'fehlerberichte'"
)
_AKTIONEN_ALT = "'sehen', 'erstellen', 'bearbeiten', 'loeschen', 'zeitplan_sehen', 'zeitplan_beantragen'"

_WURZEL_TITEL = "Geschäftsführung"

def _zeit_spalten() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _mandant_spalte(tabelle: str) -> tuple[sa.Column, sa.ForeignKeyConstraint]:
    return (
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name=f"fk_{tabelle}_mandant_id_mandanten"),
    )


def _rls_und_trigger(tabelle: str, *, updated_at: bool = True) -> None:
    if updated_at:
        op.execute(
            f"CREATE TRIGGER trg_{tabelle}_updated_at BEFORE UPDATE ON {tabelle} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    _rls(tabelle)


def _rls(tabelle: str) -> None:
    op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {tabelle} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY mandant_isolation ON {tabelle}
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


def _recht_tabelle(tabelle: str, ziel_spalte: str, ziel_tabelle: str) -> None:
    mandant_col, mandant_fk = _mandant_spalte(tabelle)
    op.create_table(
        tabelle,
        _uuid_pk(),
        mandant_col,
        sa.Column(ziel_spalte, postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bereich", sa.Text(), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("wirkung", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        *_zeit_spalten(),
        mandant_fk,
        sa.ForeignKeyConstraint(
            [ziel_spalte], [f"{ziel_tabelle}.id"], name=f"fk_{tabelle}_{ziel_spalte}_{ziel_tabelle}", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(ziel_spalte, "bereich", "aktion", name=f"uq_{tabelle}_ziel"),
        sa.CheckConstraint("wirkung IN ('erlauben', 'verweigern')", name="wirkung_valid"),
        sa.CheckConstraint(f"scope IS NULL OR scope IN ({_SCOPES})", name="scope_valid"),
    )
    op.create_index(f"ix_{tabelle}_mandant_id", tabelle, ["mandant_id"])
    _rls_und_trigger(tabelle)


def upgrade() -> None:
    # RLS ist FORCE: ohne Super-Admin-Flag sieht die Datenmigration keine Zeile.
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    mandant_col, mandant_fk = _mandant_spalte("org_einheiten")
    op.create_table(
        "org_einheiten",
        _uuid_pk(),
        mandant_col,
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("typ", sa.Text(), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archiviert_am", sa.TIMESTAMP(timezone=True), nullable=True),
        *_zeit_spalten(),
        mandant_fk,
        sa.ForeignKeyConstraint(
            ["parent_id"], ["org_einheiten.id"], name="fk_org_einheiten_parent_id_org_einheiten", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("typ IN ('bereich', 'abteilung', 'team')", name="typ_valid"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_nicht_selbst"),
    )
    op.create_index("ix_org_einheiten_mandant_parent", "org_einheiten", ["mandant_id", "parent_id"])
    _rls_und_trigger("org_einheiten")

    mandant_col, mandant_fk = _mandant_spalte("positionen")
    op.create_table(
        "positionen",
        _uuid_pk(),
        mandant_col,
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("typ", sa.Text(), nullable=False, server_default="linie"),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("ebene", sa.Integer(), nullable=True),
        sa.Column("org_einheit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_typ_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geplant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("soll_besetzung", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("gueltig_ab", sa.Date(), nullable=True),
        sa.Column("gueltig_bis", sa.Date(), nullable=True),
        sa.Column("archiviert_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erstellt_von", postgresql.UUID(as_uuid=True), nullable=True),
        *_zeit_spalten(),
        mandant_fk,
        sa.ForeignKeyConstraint(
            ["parent_id"], ["positionen.id"], name="fk_positionen_parent_id_positionen", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["org_einheit_id"], ["org_einheiten.id"], name="fk_positionen_org_einheit_id_org_einheiten"
        ),
        sa.ForeignKeyConstraint(
            ["account_typ_id"],
            ["account_typen.id"],
            name="fk_positionen_account_typ_id_account_typen",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["erstellt_von"], ["users.id"], name="fk_positionen_erstellt_von_users"),
        sa.CheckConstraint("typ IN ('linie', 'stabsstelle')", name="typ_valid"),
        sa.CheckConstraint("soll_besetzung >= 0", name="soll_besetzung_nicht_negativ"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_nicht_selbst"),
    )
    op.create_index("ix_positionen_mandant_parent", "positionen", ["mandant_id", "parent_id"])
    op.create_index("ix_positionen_account_typ_id", "positionen", ["account_typ_id"])
    _rls_und_trigger("positionen")

    mandant_col, mandant_fk = _mandant_spalte("position_besetzungen")
    op.create_table(
        "position_besetzungen",
        _uuid_pk(),
        mandant_col,
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("art", sa.Text(), nullable=False, server_default="regulaer"),
        sa.Column("gueltig_von", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("gueltig_bis", sa.TIMESTAMP(timezone=True), nullable=True),
        *_zeit_spalten(),
        mandant_fk,
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positionen.id"],
            name="fk_position_besetzungen_position_id_positionen",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_position_besetzungen_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("art IN ('regulaer', 'vertretung')", name="art_valid"),
        sa.CheckConstraint("gueltig_bis IS NULL OR gueltig_bis > gueltig_von", name="zeitraum_valid"),
    )
    op.create_index(
        "uq_position_besetzungen_aktiv",
        "position_besetzungen",
        ["position_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("gueltig_bis IS NULL"),
    )
    op.create_index("ix_position_besetzungen_user_id", "position_besetzungen", ["user_id"])
    op.create_index("ix_position_besetzungen_position_id", "position_besetzungen", ["position_id"])
    op.create_index("ix_position_besetzungen_mandant_id", "position_besetzungen", ["mandant_id"])
    _rls_und_trigger("position_besetzungen")

    _recht_tabelle("position_rechte", "position_id", "positionen")
    _recht_tabelle("user_rechte", "user_id", "users")

    # --- account_typ_rechte: mandant_id, scope, eigene RLS -----------------
    op.add_column("account_typ_rechte", sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE account_typ_rechte r SET mandant_id = a.mandant_id "
        "FROM account_typen a WHERE a.id = r.account_typ_id"
    )
    op.alter_column("account_typ_rechte", "mandant_id", nullable=False)
    op.create_foreign_key(
        "fk_account_typ_rechte_mandant_id_mandanten", "account_typ_rechte", "mandanten", ["mandant_id"], ["id"]
    )
    op.create_index("ix_account_typ_rechte_mandant_id", "account_typ_rechte", ["mandant_id"])
    op.add_column(
        "account_typ_rechte", sa.Column("scope", sa.Text(), nullable=False, server_default="mandant")
    )
    op.create_check_constraint("scope_valid", "account_typ_rechte", f"scope IN ({_SCOPES})")
    # Auffangnetz fuer Insert-Pfade ohne mandant_id (z.B. Tests): aus dem Account-Typ ableiten.
    op.execute(
        """
        CREATE FUNCTION account_typ_rechte_mandant_fuellen() RETURNS trigger AS $$
        BEGIN
          IF NEW.mandant_id IS NULL THEN
            SELECT mandant_id INTO NEW.mandant_id FROM account_typen WHERE id = NEW.account_typ_id;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_account_typ_rechte_mandant BEFORE INSERT ON account_typ_rechte "
        "FOR EACH ROW EXECUTE FUNCTION account_typ_rechte_mandant_fuellen()"
    )
    _rls("account_typ_rechte")
    # Validierung gegen die Registry im Code statt DB-Check.
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_bereich_valid")
    op.execute("ALTER TABLE account_typ_rechte DROP CONSTRAINT ck_account_typ_rechte_aktion_valid")

    # --- Datenmigration ----------------------------------------------------
    # Wurzel je Mandant; soll_besetzung = aktive mandant_admin (mind. 1).
    op.execute(
        f"""
        INSERT INTO positionen (mandant_id, typ, titel, soll_besetzung, reihenfolge)
        SELECT m.id, 'linie', '{_WURZEL_TITEL}',
               GREATEST(1, (SELECT count(*) FROM users u
                            WHERE u.mandant_id = m.id AND u.role = 'mandant_admin' AND u.aktiv)),
               0
        FROM mandanten m
        """
    )
    op.execute(
        """
        INSERT INTO position_besetzungen (mandant_id, position_id, user_id, art)
        SELECT u.mandant_id, p.id, u.id, 'regulaer'
        FROM users u
        JOIN positionen p ON p.mandant_id = u.mandant_id AND p.parent_id IS NULL
        WHERE u.role = 'mandant_admin' AND u.aktiv
        """
    )
    # Eine Position je Account-Typ unter der Wurzel (nur die Wurzel hat parent_id NULL).
    op.execute(
        """
        INSERT INTO positionen (mandant_id, parent_id, typ, titel, account_typ_id, soll_besetzung, reihenfolge)
        SELECT a.mandant_id, w.id, 'linie', a.name, a.id,
               GREATEST(1, (SELECT count(*) FROM users u
                            WHERE u.account_typ_id = a.id AND u.role = 'custom' AND u.aktiv)),
               a.reihenfolge
        FROM account_typen a
        JOIN positionen w ON w.mandant_id = a.mandant_id AND w.parent_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO position_besetzungen (mandant_id, position_id, user_id, art)
        SELECT u.mandant_id, p.id, u.id, 'regulaer'
        FROM users u
        JOIN positionen p ON p.mandant_id = u.mandant_id AND p.account_typ_id = u.account_typ_id
        WHERE u.role = 'custom' AND u.aktiv AND u.account_typ_id IS NOT NULL
        """
    )
    # nur_zugewiesene_kunden (anwendungsseitig) -> Scope "eigene" dort, wo die Registry ihn kennt.
    op.execute(
        f"""
        UPDATE account_typ_rechte r SET scope = 'eigene'
        FROM account_typen a
        WHERE a.id = r.account_typ_id AND a.nur_zugewiesene_kunden
          AND r.bereich IN ({_BEREICHE_MIT_EIGENE})
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.execute(
        f"DELETE FROM account_typ_rechte WHERE bereich NOT IN ({_BEREICHE_ALT}) "
        f"OR aktion NOT IN ({_AKTIONEN_ALT})"
    )
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_bereich_valid "
        f"CHECK (bereich IN ({_BEREICHE_ALT}))"
    )
    op.execute(
        "ALTER TABLE account_typ_rechte ADD CONSTRAINT ck_account_typ_rechte_aktion_valid "
        f"CHECK (aktion IN ({_AKTIONEN_ALT}))"
    )
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON account_typ_rechte")
    op.execute("ALTER TABLE account_typ_rechte NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_typ_rechte DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER IF EXISTS trg_account_typ_rechte_mandant ON account_typ_rechte")
    op.execute("DROP FUNCTION IF EXISTS account_typ_rechte_mandant_fuellen()")
    op.drop_constraint("scope_valid", "account_typ_rechte", type_="check")
    op.drop_column("account_typ_rechte", "scope")
    op.drop_index("ix_account_typ_rechte_mandant_id", table_name="account_typ_rechte")
    op.drop_constraint("fk_account_typ_rechte_mandant_id_mandanten", "account_typ_rechte", type_="foreignkey")
    op.drop_column("account_typ_rechte", "mandant_id")

    for tabelle in ("user_rechte", "position_rechte", "position_besetzungen", "positionen", "org_einheiten"):
        op.execute(f"DROP POLICY IF EXISTS mandant_isolation ON {tabelle}")
        op.drop_table(tabelle)
