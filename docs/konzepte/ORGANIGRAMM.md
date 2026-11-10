# Organigramm, Positionen und Rechte-Engine (Konzept, freigegeben 2026-10-05)

## Ausgangslage
- `users.role`: super_admin, mandant_admin, custom, loesch_ansicht, loesch_operativ.
  Nur `custom` bekommt Rechte über **einen** Account-Typ (`users.account_typ_id`);
  alle anderen Rollen haben implizit alle Rechte.
- `account_typ_rechte`: (bereich, aktion, erlaubt), keine Scopes, kein `mandant_id`,
  keine eigene RLS (nur indirekt über `account_typen`). Datenbeschränkung heute
  nur über das Flag `nur_zugewiesene_kunden` (anwendungsseitig, `zuweisung_service`).
- Bereiche/Aktionen dreifach hart verdrahtet (DB-Check, Python-Tupel, AccountTypenPage).
- Prüfungen verstreut: ~220× require_roles, ~214× require_recht, ~40 direkte role-Vergleiche.
- Keine Teams/Abteilungen/Vorgesetzten im Modell.

## Datenmodell (alle Tabellen mit mandant_id + RLS `mandant_isolation`)
- `org_einheiten`: name, typ (bereich|abteilung|team), parent_id (optional).
- `positionen`: parent_id, typ (linie|stabsstelle), titel, ebene, org_einheit_id,
  account_typ_id, geplant (bool), soll_besetzung, gueltig_ab/bis, archiviert_am, reihenfolge.
  Status abgeleitet: besetzt (aktive Besetzung) / vakant (keine) / geplant (Flag).
- `position_besetzungen`: position_id, user_id, gueltig_von, gueltig_bis, art (regulaer|vertretung).
  Historie + Mehrfachbesetzung + Vertretung.
- `position_rechte` / `user_rechte`: Overrides (bereich, aktion, wirkung erlauben|verweigern, scope).
- `account_typ_rechte` erweitert um `scope` und `mandant_id` (+ eigene RLS).
- Baum: Adjazenzliste + rekursive CTEs (Mandant < ~1000 Positionen; Umhängen = 1 UPDATE;
  Closure Table/ltree unnötig teuer beim Umhängen). Zyklusprüfung per CTE unter Sperre;
  Archivieren mit aktiven Untergebenen verboten.

## Rechte-Engine (`berechtigung_service`, einzige Stelle der Auflösung)
- Registry im Code (Bereiche, Aktionen, unterstützte Scopes je Bereich), per API
  ausgeliefert; Frontend-Matrix dynamisch. DB-Check-Constraints für bereich/aktion entfallen,
  ein Test prüft DB-Werte ⊆ Registry.
- Aktionen: sehen, erstellen, bearbeiten, loeschen, exportieren, freigeben, rechte_verwalten
  (+ bestehende Zusatzaktionen wie projekte.zeitplan_*).
- Scopes: eigene < team < teilbaum < bereich < mandant. `eigene` ersetzt nur_zugewiesene_kunden.
- Auflösung (deterministisch):
  1. Aktive Besetzungen des Users (Vertretung nur im Zeitfenster).
  2. Je Position: Account-Typ-Basis + Positions-Overrides; Positions-„verweigern“ wirkt nur
     für diese Position.
  3. Vereinigung über alle Positionen; Scope relativ zur gewährenden Position.
  4. User-Overrides; User-„verweigern“ gilt global (Deny schlägt Allow).
  5. Ohne aktive Besetzung keine Rechte (Platzhalter = Vorlage).
- Stabsstellen: Linien-Teilbaum läuft nie über eine Stabsstelle; Teilbaum einer Stabsstelle
  = nur ihre eigenen Unterpositionen. Weitere Sichten explizit vergeben.
- mandant_admin bleibt Rolle (Notfall-Admin außerhalb des Organigramms, alle Rechte).
- Durchsetzung: `require_recht` behält Signatur, nutzt intern die Engine; `scope_filter(bereich)`
  liefert erlaubte User-/Kunden-IDs für Listen; Schreib-APIs prüfen Scope pro Datensatz.
- Eskalationsschutz: nur vergeben, was man selbst (Bereich/Aktion/Scope) hat, und nur im
  eigenen Teilbaum (rechte_verwalten mit Scope mandant: mandantweit). Letzter aktiver Admin
  nicht entfernbar/herabstufbar.

## Scopes – Reichweite
team/teilbaum/bereich nur bei Daten mit zuständiger Person: Vorgänge (zugewiesener_user_id),
Termine/Zeiten (techniker_id), Projektaufgaben (zugewiesen_an), Kunden (KundeZuweisung).
Andere Bereiche bieten in der Registry nur `mandant`.

## Migration ohne Rechteverlust
- Pro Account-Typ eine Position, alle bisherigen Nutzer des Typs als Besetzung; Wurzel
  „Geschäftsführung“ mit den Mandanten-Admins.
- Bestehende Rechte → Scope `mandant`, bei nur_zugewiesene_kunden → `eigene`.
- `python -m app.cli organigramm-migration --dry-run`: effektive Rechte je User vorher/nachher.
  Golden-Test in der Suite.
- `users.account_typ_id` bleibt in der Übergangszeit (Fallback); Downgrade entfernt nur Neues.

## UI (Office)
Organigramm mit @xyflow/react (Zoom/Pan, Auf-/Zuklappen, Drag&Drop umhängen, Kontextmenü),
Darstellung besetzt/vakant/geplant/Stabsstelle (seitlich, gestrichelt); Seitenpanel mit
Stammdaten, Besetzung/Historie/Vertretung, Rechte-Matrix mit Herkunft und Diff zur Vorlage;
Account-Typen neu (dynamische Matrix, Scope, Verwendung, Systemvorlagen); „Anzeigen als …“;
Listenansicht mit CSV/PDF. DSGVO: Bereich `organigramm` mit Scope; Namen nur mit
mitarbeiterverwaltung.sehen im Scope.

## Audit
Helfer `log_aenderung(..., vorher, nachher)` für Struktur, Besetzungen, Account-Typen, Rechte.

## Entscheidungen
- Mehrfachpositionen: Vereinigung, User-Deny global, Positions-Deny lokal.
- Vertretung: ja, als befristete Besetzung.
- Externe (Partner, Kundenportal): außerhalb des Organigramms.

## Schritte
1. Migration 0100 (Tabellen, Scope/RLS-Nachrüstung, Registry, Datenmigration, Dry-Run-CLI)
2. Engine + Unit-/Golden-Tests, require_recht über Engine
3. Schreib-APIs, Eskalationsschutz, letzter Admin, Zyklen, Audit, RLS-Tests
4. Scope-Filter in Vorgänge/Termine/Zeiten/Kunden/Projektaufgaben
5. UI + E2E
6. Direkte Rollenprüfungen migrieren, Altlast `disponent` entfernen
