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
    # --- Worker-Jobs / Scheduler (kein Mandantenkontext, laufen ueber alle Mandanten) ---
    "app/services/scheduler_service.py": "Tick-Jobs ueber alle Mandanten",
    "app/services/job_runner.py": "Job-Ausfuehrung und Heartbeats des Workers",
    "app/services/job_state_service.py": "job_laeufe enthaelt systemweite Zeilen (mandant_id NULL)",
    "app/services/export_job_service.py": "Export-Jobs mandantenuebergreifend abholen",
    "app/services/s3_aufraeumen_service.py": "S3-Loeschauftraege mandantenuebergreifend abarbeiten",
    "app/services/mail_outbox_service.py": "Postausgang-Versand durch den Worker",
    "app/services/mail_sync_service.py": "IMAP-Sync aller Postfaecher durch den Worker",
    "app/services/email_ingest_service.py": "E-Mail-Import (Eingangsrechnungen) durch den Worker",
    "app/services/mahnwesen_service.py": "Mahnlauf ueber alle Mandanten",
    "app/services/kreditorenbuchhaltung_service.py": "Faelligkeits-/Skonto-Erinnerungen ueber alle Mandanten",
    "app/services/fehlerbericht_service.py": "Aufbewahrungsloeschung der Fehlerberichte ueber alle Mandanten",
    "app/services/datenimport/lauf.py": "Aufraeumen alter Importquellen/-berichte ueber alle Mandanten",
    "app/services/health_service.py": "Heartbeat-Pruefung des Workers (job_laeufe)",
    # --- Auth-Lookups (Mandant vor der Authentifizierung noch unbekannt) ---
    "app/services/auth_service.py": "Login-Lookup: E-Mail ist plattformweit eindeutig",
    "app/services/kundenportal_auth_service.py": "Pre-Auth-Lookup Kundenportal",
    "app/services/partner_auth_service.py": "Pre-Auth-Lookup Partnerportal",
    "app/services/audit_service.py": "Login-Fehlschlag in eigener Transaktion protokollieren",
    "app/api/deps.py": "Token-Version pruefen (vor Tenant-Session) und Session fuer super_admin",
    "app/api/routes/auth.py": "/me und Passwortaenderung: auch fuer super_admin/Impersonation",
    "app/api/routes/mfa.py": "MFA-Einrichtung: auch fuer super_admin/Impersonation",
    "app/api/routes/kundenportal_auth.py": "Kundenportal-Login/Link-Info vor Authentifizierung",
    "app/api/routes/partner_auth.py": "Partnerportal-Login/Einladung vor Authentifizierung",
    "app/api/routes/stream.py": "Stream-Ticket-Pruefung (Token-Version) vor Tenant-Session",
    "app/api/routes/users.py": "selbstbezogene Praeferenzen (Navigation), auch fuer super_admin",
    # --- Super-Admin-Routen / Plattform ---
    "app/api/routes/impersonation.py": "super_admin laedt den Mandanten fuer Impersonation",
    "app/api/routes/fehlerberichte.py": "Service-Token-Schnittstelle fuer Fehlerberichte (kein Nutzerkontext)",
    "app/api/routes/public_rechtliches.py": "oeffentliche Rechtstexte ohne Login (Mandant per Portal-Slug)",
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
