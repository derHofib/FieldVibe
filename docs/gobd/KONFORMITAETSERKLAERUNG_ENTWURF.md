# Konformitätserklärung (Entwurf) – GoBD-Merkmale und ihre Umsetzung in FieldVibe

> **Keine Zertifizierung. Juristisch/steuerlich zu prüfen.** Dies ist eine Selbstauskunft des Herstellers/Betreibers über
> die technische Umsetzung. Sie ersetzt weder ein Testat noch eine Prüfung durch Steuerberater/-in, Wirtschaftsprüfer/-in oder
> die Finanzverwaltung. Die GoBD verlangen zudem organisatorische Maßnahmen im Betrieb (Verfahrensdokumentation, IKS), die
> **nicht** durch Software erfüllt werden. Aussagen mit Status „teilweise“ oder „offen“ sind bewusst so benannt.
>
> Rechtsstand: GoBD (BMF 28.11.2019, geändert 11.03.2024), AO/HGB/UStG nach BEG IV (ab 01.01.2025).
> Stand der Software: Migration 0114. `[[BETREIBER: Version/Datum eintragen, Unterschrift verantwortlich]]`

Statuslegende: **erfüllt** = technisch umgesetzt und getestet · **teilweise** = umgesetzt mit benannter Lücke ·
**organisatorisch** = muss der Betrieb regeln · **offen** = nicht umgesetzt.

## 1. Checkliste

| # | GoBD-Merkmal (Rz.) | Umsetzung im System | Code-Verweis | Status |
|---|---|---|---|---|
| 1 | **Nachvollziehbarkeit** (Rz. 30 ff.): Beleg → Buchung → Auswertung und umgekehrt | Rechnungsnummer → Positionen → Zahlungen → Export; Herkunft der Positionen (`quelle`, `vorgang_id`); Ereignisse je Beleg im Protokoll | `models/rechnung.py`, `services/rechnung_service.py`, `routes/audit.py` | erfüllt |
| 2 | **Nachprüfbarkeit** (Rz. 32): Verfahrensdokumentation | Muster liegt bei, betriebsspezifische Angaben fehlen naturgemäß | `docs/gobd/VERFAHRENSDOKUMENTATION.md` | organisatorisch |
| 3 | **Vollständigkeit** (Rz. 36 ff.): kein Geschäftsvorfall geht verloren | Nummernkreis mit atomarem Zähler, Nummern werden nie wiederverwendet; gelöschte Entwürfe hinterlassen erklärbare Lücke mit Protokolleintrag. **Lücke:** Entwürfe erhalten die Nummer bereits bei Anlage | `services/numbering_service.py`, Aktion `rechnung_entwurf_geloescht` | teilweise |
| 4 | **Richtigkeit** (Rz. 41 ff.) | Pflichtangaben- und Steuerprüfung vor Versand (§ 14 UStG, EN 16931, Kleinunternehmer, § 13b); Summen aus Positionen | `rechnung_service.pruefe_versand`, `steuer_service` | erfüllt |
| 5 | **Zeitgerechte Buchung/Erfassung** (Rz. 45 ff.) | Versandzeitpunkt serverseitig (`versendet_am`), Erfassungszeitpunkt `created_at` jeder Zahlung; Zahlungsdatum rückdatierbar, aber mit Erfassungszeit; Protokollzeit vom Datenbankserver | `RechnungZahlung`, `audit_log.created_at` | erfüllt |
| 6 | **Ordnung** (Rz. 50 ff.) | Belege nach Art/Nummer, Kunden-/Lieferantenbezug, Kontenbezüge (Debitoren/Kreditoren, Erlöskonten) | `models/*`, `z3_service` (konten.csv) | erfüllt |
| 7 | **Unveränderbarkeit** (Rz. 58 ff.) Ausgangsrechnungen | Datenbank-Trigger gegen Änderung/Löschung festgeschriebener Rechnungen und ihrer Positionen; Korrektur nur per Storno/Gutschrift | Migration 0114 (`rechnungen_festschreibung`, `rechnung_positionen_festschreibung`), `tests/test_rechnung_festschreibung.py` | erfüllt (Grenze: DB-Superuser kann Trigger deaktivieren) |
| 8 | Unveränderbarkeit archivierter Dokumente | PDF/XML einmalig beim Versand erzeugt, nie überschrieben, SHA-256 in der DB, Prüf-Endpoint; optional S3 Object Lock | `rechnung_service.archiviere_pdf`, `pruefe_archiv`, `docs/gobd/OBJECT_LOCK.md` | erfüllt; Object Lock ungetestet gegen MinIO |
| 9 | Unveränderbarkeit Eingangsbelege | Original-PDF/-XML byte-identisch gespeichert, XML mit SHA-256 | `e_rechnung_empfang_service`, `Eingangsrechnung.xml_sha256` | teilweise (Hash für PDF-Belege und Altbestand fehlt) |
| 10 | Unveränderbarkeit Zahlungen, Angebotsannahme | Zahlungen nur additiv (Gegenbuchung); `angebot_annahmen` per Trigger append-only | `RechnungZahlung`, Migration 0111 | teilweise (kein Trigger auf `rechnung_zahlungen`, nur Konvention) |
| 11 | **Änderungsprotokoll** (Rz. 58, 107) | Mandanten-Protokoll: append-only (Trigger), Hash-Kette je Mandant, Verifikation, Einsicht/CSV. Fehler beim Protokollieren bricht die Transaktion ab | `services/audit_service.py`, `routes/audit.py`, Migration 0114, `tests/test_audit_mandant.py` | erfüllt |
| 12 | Protokollumfang (Anmeldung, Rechte, Beleg-Ereignisse, Exporte, Löschungen, Steuereinstellungen, Import) | siehe Verfahrensdokumentation 2.4. **Lücke:** Stammdatenänderungen (Kunde, Material) und Lesezugriffe werden nicht protokolliert; Super-Admin-Plattformaktionen mit nur Plattformbezug stehen im Plattformprotokoll | `audit_service`, Aufrufer in `routes/*` | teilweise |
| 13 | **Aufbewahrung** (Rz. 80 ff.): Fristen nach Belegart | 8/6/10 Jahre, Fristbeginn Jahresende, Übergangsregel BEG IV; Löschsperre bis Fristende; Löschvorschlagsliste ohne Automatik | `services/aufbewahrung_service.py`, `papierkorb_service.GobdLoeschsperre`, `tests/test_aufbewahrung.py` | erfüllt; Ablaufhemmung nicht abgebildet |
| 14 | Verfügbarkeit/Lesbarkeit während der Frist (Rz. 85 ff.) | Daten im Produktivsystem; maschinenlesbare Exporte unabhängig von FieldVibe (CSV/JSON/XML/PDF) | `vollexport_service`, `z3_service` | erfüllt |
| 15 | **Datenzugriff** (Rz. 158 ff.) Z1 | Lesender Zugang über regulären Account mit Leserechten möglich; kein eigener Prüferzugang | Rechte-Matrix | organisatorisch |
| 16 | Datenzugriff Z2 | Auswertungen: OP-Liste, UStVA, DATEV, CSV | `routes/auswertung.py` | erfüllt |
| 17 | Datenzugriff **Z3** (Datenträgerüberlassung) | ZIP mit `index.xml` + CSV (CP1252, Dezimalkomma), Zeitraum wählbar. **`index.xml` nicht gegen IDEA/DTD validiert**, DTD nicht beigelegt | `services/z3_service.py`, `tests/test_export_z3.py` | teilweise (Validierung offen) |
| 18 | Datenübertragbarkeit (Art. 20 DSGVO, EU Data Act) | Vollexport mit Manifest (SHA-256), README, nur `mandant_admin`, protokolliert | `vollexport_service`, `export_job_service` | erfüllt |
| 19 | **Mandantentrennung** | Row-Level-Security mit erzwungener Policy; Objektschlüssel mit Mandantenpräfix; Exporte prüfen Schlüssel zusätzlich | Migrationen, `storage_service.key_gehoert_zu_mandant`, `tests/test_rls_*`, `tests/test_export_vollexport.py` | erfüllt (Altobjekte ohne Präfix: Zuordnung über RLS-Zeile) |
| 20 | **Internes Kontrollsystem** (Rz. 100 ff.) | Rollen/Rechte, Eskalationsschutz, MFA optional/Pflicht je Betrieb, Papierkorb-Trennung, Stichprobenfunktionen (Archivprüfung, Kettenprüfung) | `berechtigung_service`, `mfa_service` | teilweise; Kontrollen selbst organisatorisch |
| 21 | **Datensicherung** (Rz. 103) | Tägliches Backup, Prüfsummen, Test-Restore | `scripts/backup*.sh`, `docs/DEPLOYMENT.md` | teilweise (RPO bis 24 h, nicht atomar) |
| 22 | E-Rechnung (§ 14 UStG n. F.) | Erzeugung ZUGFeRD/XRechnung, Empfang mit Archivierung des Originals | `e_invoice_service`, `e_rechnung_empfang_service` | erfüllt laut Konzept; Konformitätsprüfung siehe `docs/konzepte/E_RECHNUNG_PRUEFUNG.md` |
| 23 | Kassenführung/Kassensicherungsverordnung | Nicht Gegenstand von FieldVibe (Barzahlungen werden als Zahlungsbuchung erfasst, keine Kassenfunktion) | – | nicht zutreffend |

## 2. Bekannte Lücken und Abgrenzungen (Zusammenfassung)

1. Z3-`index.xml` und Tabellenformat sind aus dem öffentlich bekannten Beschreibungsstandard rekonstruiert, **nicht mit IDEA geprüft**.
2. Object Lock ist optional und nicht gegen echtes MinIO getestet.
3. Datenbank-Superuser (Betreiber) können Trigger abschalten; die Hash-Kette und die Archivprüfung machen Eingriffe erkennbar,
   verhindern sie aber nicht. Das Abschneiden des Protokollendes erkennt nur, wer den Kettenkopf extern festhält.
4. Kein Trigger auf `rechnung_zahlungen` (nur Konvention „additiv“).
5. Die Ablaufhemmung der Aufbewahrungsfrist (§ 147 Abs. 3 Satz 5 AO) ist nicht abgebildet.
6. Protokolliert werden Beleg-, Sicherheits-, Export- und Löschereignisse, nicht jede Stammdatenänderung und keine Lesezugriffe.
7. Das DATEV-Format ist noch nicht per Testimport abgenommen (`docs/BACKLOG.md` 10).
8. Nummern von Rechnungsentwürfen werden bei Anlage vergeben; gelöschte Entwürfe erzeugen Lücken (im Protokoll erklärbar).

## 3. Prüfnachweise im Repository

`pytest backend/tests` (u. a. `test_audit_mandant.py`, `test_rechnung_festschreibung.py`, `test_aufbewahrung.py`,
`test_purge_s3.py`, `test_export_vollexport.py`, `test_export_z3.py`, `test_migration_0114.py`). Die Tests belegen das beschriebene
Verhalten der Software, nicht die Eignung für einen konkreten Betrieb.
