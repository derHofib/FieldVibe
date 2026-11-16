"""RLS-Bypass an die DB-Rolle fieldvibe_system binden (Phase 3).

Bisher umging jede Policy die Mandantentrennung ueber die Session-Variable
app.is_super_admin = 'true' -- die kann aber jede App-Verbindung selbst setzen
(z. B. nach einer SQL-Injection). Ab jetzt laeuft system_session ueber eine
eigene Rolle mit BYPASSRLS (DATABASE_URL_SYSTEM); die Policies kennen nur noch
app.current_mandant.

Die Bereinigung laeuft ueber pg_policies statt Tabelle fuer Tabelle und ist
strikt: weicht eine Policy von der bekannten Form ab, bricht die Migration ab,
statt zu raten. plattform_integrationen verliert beide Policies (lesbar:
USING true, schreibbar: nur super-admin) -- die Tabelle bleibt RLS+FORCE ohne
Policy, die App-Rolle hat damit keinen Zugriff, nur die System-Rolle.

Downgrade haengt die Bedingung wieder an und legt die beiden entfernten
Policies mit ihrem Originaltext neu an.

Hinweis: alembic/env.py setzt weiterhin app.is_super_admin fuer Migrationen;
das wirkt nach 0117 nicht mehr -- spaetere Migrationen mit Daten-Backfills
auf RLS-Tabellen muessen den Bypass anders loesen.

Revision ID: 0117
Revises: 0116
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0117"
down_revision: Union[str, None] = "0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# So gibt pg_policies die Teilbedingung aus (pg_get_expr-Normalform).
_SUPER = (
    "(COALESCE(NULLIF(current_setting('app.is_super_admin'::text, true), ''::text), "
    "'false'::text))::boolean"
)
_ODER = " OR " + _SUPER + ")"
_SCHLUESSEL = "is_super_admin"

# Rein super-admin-basierte bzw. permissive Policies, die ersatzlos entfallen.
_ENTFALLEN = {
    ("plattform_integrationen", "plattform_integrationen_lesbar"): (
        "CREATE POLICY plattform_integrationen_lesbar ON plattform_integrationen FOR SELECT USING (true)"
    ),
    ("plattform_integrationen", "plattform_integrationen_schreibbar"): (
        "CREATE POLICY plattform_integrationen_schreibbar ON plattform_integrationen FOR ALL "
        f"USING ({_SUPER}) WITH CHECK ({_SUPER})"
    ),
}


def _policies(bind) -> list:
    return bind.execute(
        sa.text(
            "SELECT schemaname, tablename, policyname, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' ORDER BY tablename, policyname"
        )
    ).all()


def _ohne_super(ausdruck: str | None, wo: str) -> str | None:
    if ausdruck is None:
        return None
    if _SCHLUESSEL not in ausdruck:
        raise RuntimeError(f"Policy {wo}: unerwartete Form ohne is_super_admin: {ausdruck}")
    if not (ausdruck.startswith("(") and ausdruck.endswith(_ODER)):
        raise RuntimeError(f"Policy {wo}: unbekanntes Muster, keine automatische Bereinigung: {ausdruck}")
    rest = ausdruck[1 : -len(_ODER)]
    if _SCHLUESSEL in rest or not rest:
        raise RuntimeError(f"Policy {wo}: unbekanntes Muster, keine automatische Bereinigung: {ausdruck}")
    return rest


def upgrade() -> None:
    bind = op.get_bind()
    for p in _policies(bind):
        wo = f"{p.tablename}.{p.policyname}"
        if (p.tablename, p.policyname) in _ENTFALLEN:
            op.execute(f'DROP POLICY "{p.policyname}" ON "{p.tablename}"')
            continue
        qual = _ohne_super(p.qual, wo)
        check = _ohne_super(p.with_check, wo) if p.with_check is not None else None
        if qual is None:
            raise RuntimeError(f"Policy {wo} ohne USING-Ausdruck, unbekannte Form")
        klausel = f"USING ({qual})" + (f" WITH CHECK ({check})" if check else "")
        op.execute(f'ALTER POLICY "{p.policyname}" ON "{p.tablename}" {klausel}')

    rest = [f"{p.tablename}.{p.policyname}" for p in _policies(bind) if _SCHLUESSEL in f"{p.qual}{p.with_check}"]
    if rest:
        raise RuntimeError(f"is_super_admin nach der Bereinigung noch in Policies: {rest}")


def downgrade() -> None:
    bind = op.get_bind()
    for p in _policies(bind):
        qual = f"({p.qual}{_ODER}"
        check = f"({p.with_check}{_ODER}" if p.with_check is not None else None
        klausel = f"USING ({qual})" + (f" WITH CHECK ({check})" if check else "")
        op.execute(f'ALTER POLICY "{p.policyname}" ON "{p.tablename}" {klausel}')
    for (tabelle, _name), sql in _ENTFALLEN.items():
        op.execute(sql)
