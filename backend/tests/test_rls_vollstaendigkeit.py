"""Vollstaendigkeitspruefung der Mandanten-Isolation direkt im Datenbankkatalog:
jede Tabelle mit mandant_id muss RLS aktiv + erzwungen haben und eine Policy auf
app.current_mandant besitzen. Eine neue Tabelle ohne RLS faellt hier auf, bevor
sie in Produktion Daten mandantenuebergreifend sichtbar macht."""

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings

# Tabellen OHNE mandant_id. Eintraege nur mit
# Begruendung; ein Eintrag, den es nicht mehr gibt, ist ein Fehler.
OHNE_MANDANT_ID: dict[str, str] = {
    "mandanten": (
        "Wurzel der Mandantenhierarchie; RLS ueber id = app.current_mandant "
        "(Policy mandant_isolation)"
    ),
    "plattform_integrationen": (
        "plattformweiter SMTP-Fallback; seit 0117 RLS+FORCE ohne jede Policy: nur die "
        "System-Rolle (BYPASSRLS) kommt heran"
    ),
    "dsgvo_dokumente": (
        "plattformweite Compliance-Dokumente (AVV-Vorlage, Impressum ...), "
        "bewusst ohne RLS; Zugriff nur ueber super_admin-Route und Download-URLs"
    ),
    "alembic_version": "Migrationsstand von Alembic, keine Fachdaten",
    "ki_clients": (
        "per Dynamic Client Registration angelegte OAuth-Clients des MCP-Servers (Migration 0118): "
        "die Registrierung passiert vor jedem Login ohne Mandanten-Kontext, enthalten sind nur "
        "Client-Metadaten; die Mandantenbindung liegt in ki_verbindungen (RLS)"
    ),
}

# Teilmenge von OHNE_MANDANT_ID, bei der RLS dennoch aktiv und erzwungen sein muss.
OHNE_MANDANT_ID_ABER_MIT_RLS = {"mandanten", "plattform_integrationen"}


@pytest.fixture(scope="module")
def katalog():
    engine = create_engine(get_settings().database_url_sync)
    with engine.connect() as conn:
        tabellen = conn.execute(
            text(
                """
                SELECT c.relname AS name, c.relrowsecurity AS rls, c.relforcerowsecurity AS erzwungen,
                       EXISTS (
                         SELECT 1 FROM information_schema.columns k
                         WHERE k.table_schema = 'public' AND k.table_name = c.relname
                           AND k.column_name = 'mandant_id'
                       ) AS hat_mandant_id
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                """
            )
        ).all()
        policies = conn.execute(
            text(
                "SELECT tablename, policyname, qual, with_check FROM pg_policies "
                "WHERE schemaname = 'public'"
            )
        ).all()
    engine.dispose()
    pol: dict[str, list] = {}
    for p in policies:
        pol.setdefault(p.tablename, []).append(p)
    return tabellen, pol


def _mandanten_policy(policies: list) -> bool:
    return any(
        "app.current_mandant" in (p.qual or "") or "app.current_mandant" in (p.with_check or "")
        for p in policies
    )


def test_jede_mandantentabelle_hat_erzwungene_rls_und_policy(katalog):
    tabellen, pol = katalog
    fehler = []
    for t in tabellen:
        if not t.hat_mandant_id:
            continue
        if not t.rls:
            fehler.append(f"{t.name}: ROW LEVEL SECURITY nicht aktiviert")
        if not t.erzwungen:
            fehler.append(f"{t.name}: FORCE ROW LEVEL SECURITY fehlt")
        if not _mandanten_policy(pol.get(t.name, [])):
            fehler.append(f"{t.name}: keine Policy auf app.current_mandant")
        for p in pol.get(t.name, []):
            if (p.qual or "").strip() == "true":
                fehler.append(f"{t.name}: Policy {p.policyname} mit USING (true) oeffnet die Tabelle fuer alle")
    assert not fehler, "RLS-Luecken:\n" + "\n".join(fehler)


def test_tabellen_ohne_mandant_id_stehen_in_der_ausnahmeliste(katalog):
    tabellen, _ = katalog
    ohne = {t.name for t in tabellen if not t.hat_mandant_id}
    unbekannt = sorted(ohne - OHNE_MANDANT_ID.keys())
    assert not unbekannt, "\n".join(
        f"Neue Tabelle {name}: mandant_id + RLS ergaenzen oder begruendet in die "
        "Ausnahmeliste OHNE_MANDANT_ID aufnehmen"
        for name in unbekannt
    )
    veraltet = sorted(OHNE_MANDANT_ID.keys() - ohne)
    assert not veraltet, (
        f"Ausnahmeliste enthaelt Tabellen, die nicht (mehr) ohne mandant_id existieren: {veraltet} "
        "-- Eintrag aus OHNE_MANDANT_ID entfernen"
    )


def test_ausnahmen_mit_rls_haben_rls_erzwungen(katalog):
    tabellen, _ = katalog
    nach_name = {t.name: t for t in tabellen}
    for name in OHNE_MANDANT_ID_ABER_MIT_RLS:
        assert nach_name[name].rls and nach_name[name].erzwungen, f"{name}: RLS nicht aktiv/erzwungen"


def test_plattform_integrationen_hat_rls_aber_keine_policy(katalog):
    tabellen, pol = katalog
    t = next(t for t in tabellen if t.name == "plattform_integrationen")
    assert t.rls and t.erzwungen
    assert pol.get("plattform_integrationen", []) == []


def test_keine_policy_kennt_mehr_is_super_admin(katalog):
    _, pol = katalog
    treffer = [
        f"{name}.{p.policyname}"
        for name, ps in pol.items()
        for p in ps
        if "is_super_admin" in f"{p.qual}{p.with_check}"
    ]
    assert not treffer, f"Policies mit app.is_super_admin: {treffer}"
