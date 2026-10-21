"""GoBD-Paket: Mandanten-Audit-Log (append-only, Hash-Kette), Festschreibung,
Aufbewahrung, Purge-Aufraeumliste, Mandanten-Vollexport.

Audit: audit_log wird erweitert statt dupliziert (akteur_typ, request_id, ip,
legacy) und per Trigger append-only (UPDATE/DELETE verboten, auch fuer den
Tabellenbesitzer; TRUNCATE bleibt fuer Test-Cleanup moeglich). Die
Hash-Verkettung steht bewusst in einer eigenen, ebenfalls append-only Tabelle
audit_log_siegel: die Eintraege selbst muessen nie nachtraeglich veraendert
werden, das Siegel entsteht erst kurz vor dem COMMIT (Advisory-Lock je Mandant
nur dort). Zeilen, die vor dieser Migration existierten, sind legacy und ohne
Siegel.

Festschreibung: rechnungen bekommt pdf_sha256/xml_sha256 (SHA-256 des beim Versand
archivierten PDF bzw. der XML). Trigger verhindern, dass eine Rechnung ausserhalb des
Entwurfs in ihren Kernfeldern geaendert oder geloescht wird und dass ihre Positionen
geaendert/geloescht werden. Ausnahmen: Zeilen, die in derselben Transaktion angelegt
wurden (Storno-/Gutschriftsbelege entstehen als versendet und werden danach noch
befuellt), erlaubte Folgefelder (Status, Zahlungs-/Mahnfelder, Archiv-Keys und -Hashes
einmalig von NULL auf einen Wert) und das endgueltige Loeschen nach Fristende
(Session-Variable app.gobd_loeschfreigabe, gesetzt von papierkorb_service.purge).

Downgrade ist verlustbehaftet: Siegel, Hash-Spalten und neue Spalten gehen verloren.

Revision ID: 0114
Revises: 0113
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0114"
down_revision: Union[str, None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AKTEUR_TYPEN = ("user", "portal", "system", "partner")


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


def _append_only(table: str) -> None:
    funktion = f"{table}_append_only"
    op.execute(
        f"""
        CREATE FUNCTION {funktion}() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION '{table} ist append-only (% nicht erlaubt)', TG_OP
            USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_append_only
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {funktion}()
        """
    )


def _append_only_entfernen(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only()")


# Zeile wurde in der laufenden Transaktion angelegt (oder zuletzt geaendert): dann
# darf sie noch fertig befuellt werden. xmin einer Zeile aus einer Savepoint-
# Unter-Transaktion weicht ab; das Anlegen in einem Savepoint ist hier nicht vorgesehen.
_RECHNUNGEN_TRIGGER = """
CREATE FUNCTION rechnungen_festschreibung() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'entwurf'
       AND OLD.xmin <> pg_current_xact_id()::xid
       AND coalesce(current_setting('app.gobd_loeschfreigabe', true), '') <> 'true' THEN
      RAISE EXCEPTION 'Festgeschriebene Rechnung % darf nicht geloescht werden', OLD.rechnungsnummer
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
  END IF;

  IF OLD.status = 'entwurf' OR OLD.xmin = pg_current_xact_id()::xid THEN
    RETURN NEW;
  END IF;

  IF NEW.status = 'entwurf' THEN
    RAISE EXCEPTION 'Rechnung % ist festgeschrieben, der Status darf nicht auf entwurf zurueck', OLD.rechnungsnummer
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF (NEW.mandant_id, NEW.kunde_id, NEW.vorgang_id, NEW.rechnungsnummer, NEW.leistungsdatum,
      NEW.betrag_netto, NEW.mwst_satz, NEW.faellig_am, NEW.erstellt_von, NEW.versendet_am,
      NEW.ist_storno, NEW.storniert_rechnung_id, NEW.rechnungsart, NEW.angebot_id,
      NEW.bezug_rechnung_id, NEW.gutschrift_grund)
     IS DISTINCT FROM
     (OLD.mandant_id, OLD.kunde_id, OLD.vorgang_id, OLD.rechnungsnummer, OLD.leistungsdatum,
      OLD.betrag_netto, OLD.mwst_satz, OLD.faellig_am, OLD.erstellt_von, OLD.versendet_am,
      OLD.ist_storno, OLD.storniert_rechnung_id, OLD.rechnungsart, OLD.angebot_id,
      OLD.bezug_rechnung_id, OLD.gutschrift_grund) THEN
    RAISE EXCEPTION 'Rechnung % ist festgeschrieben, Kernfelder duerfen nicht geaendert werden', OLD.rechnungsnummer
      USING ERRCODE = 'restrict_violation';
  END IF;
  -- Einmal gesetzt, nie wieder aenderbar (NULL -> Wert ist erlaubt).
  IF (OLD.pdf_object_key IS NOT NULL AND NEW.pdf_object_key IS DISTINCT FROM OLD.pdf_object_key)
     OR (OLD.xml_object_key IS NOT NULL AND NEW.xml_object_key IS DISTINCT FROM OLD.xml_object_key)
     OR (OLD.pdf_sha256 IS NOT NULL AND NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256)
     OR (OLD.xml_sha256 IS NOT NULL AND NEW.xml_sha256 IS DISTINCT FROM OLD.xml_sha256)
     OR (OLD.e_rechnung_profil IS NOT NULL AND NEW.e_rechnung_profil IS DISTINCT FROM OLD.e_rechnung_profil)
     OR (OLD.leitweg_id IS NOT NULL AND NEW.leitweg_id IS DISTINCT FROM OLD.leitweg_id) THEN
    RAISE EXCEPTION 'Rechnung %: Archivangaben sind festgeschrieben', OLD.rechnungsnummer
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_POSITIONEN_TRIGGER = """
CREATE FUNCTION rechnung_positionen_festschreibung() RETURNS trigger AS $$
DECLARE
  r_status text;
  r_neu boolean;
  r_nummer text;
BEGIN
  SELECT status, xmin = pg_current_xact_id()::xid, rechnungsnummer INTO r_status, r_neu, r_nummer
    FROM rechnungen WHERE id = OLD.rechnung_id;
  -- Rechnung schon weg (Kaskade beim endgueltigen Loeschen): die Entscheidung
  -- ueber das Loeschen traf der Trigger auf rechnungen.
  IF NOT FOUND OR r_status = 'entwurf' OR r_neu THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;

  IF TG_OP = 'DELETE' THEN
    IF coalesce(current_setting('app.gobd_loeschfreigabe', true), '') = 'true' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'Positionen der festgeschriebenen Rechnung % duerfen nicht geloescht werden', r_nummer
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- Nur das Aufloesen von Verweisen (FK ... ON DELETE SET NULL) bleibt erlaubt.
  IF (NEW.mandant_id, NEW.rechnung_id, NEW.position, NEW.beschreibung, NEW.menge, NEW.einheit,
      NEW.einzelpreis, NEW.steuer_kategorie, NEW.steuer_satz, NEW.steuer_grund, NEW.steuer_grund_text,
      NEW.quelle, NEW.abschlag_rechnung_id, NEW.bezug_position_id)
     IS DISTINCT FROM
     (OLD.mandant_id, OLD.rechnung_id, OLD.position, OLD.beschreibung, OLD.menge, OLD.einheit,
      OLD.einzelpreis, OLD.steuer_kategorie, OLD.steuer_satz, OLD.steuer_grund, OLD.steuer_grund_text,
      OLD.quelle, OLD.abschlag_rechnung_id, OLD.bezug_position_id)
     OR (NEW.vorgang_id IS DISTINCT FROM OLD.vorgang_id AND NEW.vorgang_id IS NOT NULL)
     OR (NEW.lv_position_id IS DISTINCT FROM OLD.lv_position_id AND NEW.lv_position_id IS NOT NULL)
     OR (NEW.material_id IS DISTINCT FROM OLD.material_id AND NEW.material_id IS NOT NULL) THEN
    RAISE EXCEPTION 'Positionen der festgeschriebenen Rechnung % duerfen nicht geaendert werden', r_nummer
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    # --- Audit ---------------------------------------------------------
    op.add_column(
        "audit_log",
        sa.Column("akteur_typ", sa.Text(), nullable=False, server_default="user"),
    )
    op.add_column("audit_log", sa.Column("request_id", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("ip", sa.Text(), nullable=True))
    op.add_column(
        "audit_log", sa.Column("legacy", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    # Altbestand: ohne Siegel, Akteur nur anhand actor_user_id ableitbar. Muss
    # vor dem Append-only-Trigger passieren.
    op.execute("UPDATE audit_log SET legacy = true")
    op.execute("UPDATE audit_log SET akteur_typ = 'system' WHERE actor_user_id IS NULL")
    op.create_check_constraint(
        op.f("ck_audit_log_akteur_typ_valid"), "audit_log", f"akteur_typ IN {_AKTEUR_TYPEN}"
    )
    op.create_index("ix_audit_log_mandant_id_created_at", "audit_log", ["mandant_id", "created_at"])
    _append_only("audit_log")

    op.create_table(
        "audit_log_siegel",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("audit_log_id", sa.BigInteger(), nullable=False),
        sa.Column("vorgaenger_hash", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_audit_log_siegel_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["audit_log_id"], ["audit_log.id"], name="fk_audit_log_siegel_audit_log_id_audit_log"),
        sa.UniqueConstraint("mandant_id", "seq", name="uq_audit_log_siegel_mandant_id_seq"),
        sa.UniqueConstraint("audit_log_id", name="uq_audit_log_siegel_audit_log_id"),
        sa.CheckConstraint("char_length(hash) = 64 AND char_length(vorgaenger_hash) = 64", name=op.f("ck_audit_log_siegel_hash_laenge")),
    )
    _enable_rls("audit_log_siegel")
    _append_only("audit_log_siegel")

    # --- Festschreibung ----------------------------------------------------
    op.add_column("rechnungen", sa.Column("pdf_sha256", sa.Text(), nullable=True))
    op.add_column("rechnungen", sa.Column("xml_sha256", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_rechnungen_pdf_sha256_format"), "rechnungen", "pdf_sha256 IS NULL OR pdf_sha256 ~ '^[0-9a-f]{64}$'"
    )
    op.create_check_constraint(
        op.f("ck_rechnungen_xml_sha256_format"), "rechnungen", "xml_sha256 IS NULL OR xml_sha256 ~ '^[0-9a-f]{64}$'"
    )
    op.execute(_RECHNUNGEN_TRIGGER)
    op.execute(
        """
        CREATE TRIGGER trg_rechnungen_festschreibung
        BEFORE UPDATE OR DELETE ON rechnungen
        FOR EACH ROW EXECUTE FUNCTION rechnungen_festschreibung()
        """
    )
    op.execute(_POSITIONEN_TRIGGER)
    op.execute(
        """
        CREATE TRIGGER trg_rechnung_positionen_festschreibung
        BEFORE UPDATE OR DELETE ON rechnung_positionen
        FOR EACH ROW EXECUTE FUNCTION rechnung_positionen_festschreibung()
        """
    )

    # --- Objektspeicher aufraeumen ------------------------------------------
    op.create_table(
        "s3_loeschauftraege",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("anlass", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="offen"),
        sa.Column("versuche", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("naechster_versuch_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("letzter_fehler", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("erledigt_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_s3_loeschauftraege_mandant_id_mandanten"),
        sa.CheckConstraint("status IN ('offen', 'erledigt', 'fehler')", name=op.f("ck_s3_loeschauftraege_status_valid")),
        sa.CheckConstraint("prefix LIKE '%/'", name=op.f("ck_s3_loeschauftraege_prefix_endet_mit_schraegstrich")),
    )
    op.create_index("ix_s3_loeschauftraege_status_naechster_versuch_am", "s3_loeschauftraege", ["status", "naechster_versuch_am"])
    op.create_index("ix_s3_loeschauftraege_mandant_id", "s3_loeschauftraege", ["mandant_id"])
    _enable_rls("s3_loeschauftraege")

    # --- Mandanten-Exporte (Vollexport, Z3) ---------------------------------
    op.create_table(
        "mandant_exporte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("art", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="wartend"),
        sa.Column("parameter", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("angefordert_von", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("angefordert_am", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("gestartet_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("fertig_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("laeuft_ab_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("groesse_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("anzahl_dateien", sa.Integer(), nullable=True),
        sa.Column("fehler", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandanten.id"], name="fk_mandant_exporte_mandant_id_mandanten"),
        sa.ForeignKeyConstraint(["angefordert_von"], ["users.id"], name="fk_mandant_exporte_angefordert_von_users"),
        sa.CheckConstraint("art IN ('vollexport', 'z3')", name=op.f("ck_mandant_exporte_art_valid")),
        sa.CheckConstraint(
            "status IN ('wartend', 'laeuft', 'fertig', 'fehler', 'abgelaufen')",
            name=op.f("ck_mandant_exporte_status_valid"),
        ),
    )
    op.create_index("ix_mandant_exporte_mandant_id_angefordert_am", "mandant_exporte", ["mandant_id", "angefordert_am"])
    op.create_index(
        "uq_mandant_exporte_ein_aktiver",
        "mandant_exporte",
        ["mandant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('wartend', 'laeuft')"),
    )
    _enable_rls("mandant_exporte")


def downgrade() -> None:
    op.execute("SET LOCAL app.is_super_admin = 'true'")

    op.execute("DROP POLICY IF EXISTS mandant_isolation ON mandant_exporte")
    op.drop_table("mandant_exporte")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON s3_loeschauftraege")
    op.drop_table("s3_loeschauftraege")

    op.execute("DROP TRIGGER IF EXISTS trg_rechnung_positionen_festschreibung ON rechnung_positionen")
    op.execute("DROP FUNCTION IF EXISTS rechnung_positionen_festschreibung()")
    op.execute("DROP TRIGGER IF EXISTS trg_rechnungen_festschreibung ON rechnungen")
    op.execute("DROP FUNCTION IF EXISTS rechnungen_festschreibung()")
    op.drop_constraint(op.f("ck_rechnungen_xml_sha256_format"), "rechnungen", type_="check")
    op.drop_constraint(op.f("ck_rechnungen_pdf_sha256_format"), "rechnungen", type_="check")
    op.drop_column("rechnungen", "xml_sha256")
    op.drop_column("rechnungen", "pdf_sha256")

    _append_only_entfernen("audit_log_siegel")
    op.execute("DROP POLICY IF EXISTS mandant_isolation ON audit_log_siegel")
    op.drop_table("audit_log_siegel")

    _append_only_entfernen("audit_log")
    op.drop_index("ix_audit_log_mandant_id_created_at", table_name="audit_log")
    op.drop_constraint(op.f("ck_audit_log_akteur_typ_valid"), "audit_log", type_="check")
    op.drop_column("audit_log", "legacy")
    op.drop_column("audit_log", "ip")
    op.drop_column("audit_log", "request_id")
    op.drop_column("audit_log", "akteur_typ")
