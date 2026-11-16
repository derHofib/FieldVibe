"""Architekturtest: system_session() umgeht die Mandanten-RLS komplett. Jede
Datei, die es benutzt, steht bewusst in der Allowlist unten; neue Verwendungen
muessen hier begruendet werden, nicht still durchrutschen. Die Liste soll nur
schrumpfen -- ein Eintrag ohne Verwendung ist ebenfalls ein Fehler."""

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_APP = _BACKEND / "app"
_DEFINITION = "app/db/session.py"

SYSTEM_SESSION_ALLOWLIST: dict[str, str] = {
    # --- Gebuendelte Cross-Tenant-Lookups (schmale Rueckgabewerte, danach tenant_session) ---
    "app/services/system_lookups.py": "Pre-Auth-Lookups (E-Mail/Token), Konten ohne Mandant, Fehlerbericht-Service-API",
    "app/services/worker_system.py": "Worker: aktive Mandanten, faellige IDs, Plattform-SMTP, Outbox ohne Mandant",
    # --- Worker ---
    "app/services/job_runner.py": "job_laeufe-Zeilen ohne Mandant (System-Jobs), Laden aller Laeufe",
    "app/services/health_service.py": "mandantenuebergreifende Heartbeat-/Lauf-Pruefung des Workers",
    # --- Super-Admin-Requests ---
    "app/api/deps.py": "get_db: Session fuer super_admin-Requests (plattformweite Verwaltung)",
    # --- CLI / Seed / Skripte ---
    "app/cli.py": "Administrations-CLI (Mandanten/Super-Admin anlegen)",
    "app/seed.py": "Demo-Daten anlegen",
    "app/backfill_geocode.py": "einmaliges Geocoding-Nachziehen ueber alle Mandanten",
}


def _verwendet_system_session(pfad: Path) -> bool:
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ImportFrom) and any(
            a.name == "system_session" for a in knoten.names
        ):
            return True
        if isinstance(knoten, ast.Name) and knoten.id == "system_session":
            return True
        if isinstance(knoten, ast.Attribute) and knoten.attr == "system_session":
            return True
    return False


def _verwender() -> set[str]:
    gefunden = set()
    for pfad in _APP.rglob("*.py"):
        rel = pfad.relative_to(_BACKEND).as_posix()
        if rel == _DEFINITION:
            continue
        if _verwendet_system_session(pfad):
            gefunden.add(rel)
    return gefunden


def test_system_session_nur_in_allowlist_dateien():
    neu = sorted(_verwender() - SYSTEM_SESSION_ALLOWLIST.keys())
    assert not neu, (
        "system_session() umgeht die Mandanten-RLS und darf nur an begruendeten Stellen "
        "benutzt werden. Neue Verwendung in:\n  " + "\n  ".join(neu)
        + "\nEntweder tenant_session()/get_db nutzen oder die Datei mit Begruendung in "
        "SYSTEM_SESSION_ALLOWLIST aufnehmen."
    )


def test_allowlist_enthaelt_keine_ungenutzten_eintraege():
    veraltet = sorted(SYSTEM_SESSION_ALLOWLIST.keys() - _verwender())
    assert not veraltet, (
        "Diese Dateien benutzen system_session() nicht mehr -- aus SYSTEM_SESSION_ALLOWLIST "
        "entfernen:\n  " + "\n  ".join(veraltet)
    )


def test_jeder_aufruf_hat_grund():
    ohne = []
    for pfad in _APP.rglob("*.py"):
        rel = pfad.relative_to(_BACKEND).as_posix()
        if rel == _DEFINITION:
            continue
        for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if (
                isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Name)
                and knoten.func.id == "system_session"
                and not any(k.arg == "grund" for k in knoten.keywords)
            ):
                ohne.append(f"{rel}:{knoten.lineno}")
    assert not ohne, "system_session() ohne grund=...:\n  " + "\n  ".join(ohne)
