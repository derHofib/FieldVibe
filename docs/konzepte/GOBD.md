# GoBD-Paket und Datenlebenszyklus (Roadmap 1.9)

Entscheidungen und Begründungen zu Migration 0114. Nutzerorientierte Dokumente: `docs/gobd/`.

## 1. Mandanten-Protokoll

**Erweitert, nicht dupliziert.** `audit_log` (bisher nur für Super-Admin lesbar, ~36 Aufrufer von `log_action`) bekommt
`akteur_typ`, `request_id`, `ip`, `legacy`; ein Trigger verbietet `UPDATE`/`DELETE`. Alle bestehenden Aufrufer protokollieren damit
automatisch append-only; es gibt keine zweite Tabelle mit denselben Ereignissen. Altzeilen (`legacy = true`) haben kein Siegel.

**Hash-Kette in eigener Tabelle** (`audit_log_siegel`, ebenfalls append-only): Der Eintrag selbst muss nie nachträglich geändert werden.
Das Siegel (`sha256(vorgaengerhash | kanonischer Inhalt)`, Genesis = 64 Nullen, `seq` je Mandant) entsteht im `before_commit`-Hook der
Session. Damit hält der Advisory-Lock je Mandant (`pg_advisory_xact_lock`) nur noch Siegel-INSERT und COMMIT. Würde schon beim
INSERT des Eintrags gelockt, könnten zwei Transaktionen, die danach noch Fachzeilen sperren, sich gegenseitig verklemmen
(`tests/test_audit_mandant.py::test_parallele_schreiber_...`). Gesiegelt wird aus den gelesenen DB-Werten, nicht aus Python-Objekten
(JSONB-/Zeitrundlauf).

**Audit-Fehler brechen die Fachtransaktion ab** (bewusst): GoBD verlangt, dass es keine Belegänderung ohne Protokoll gibt; ein
„Beleg ja, Protokoll nein“ wäre der schlimmere Fehler. Weil FastAPI den COMMIT der Request-Session erst nach dem Senden der Antwort
ausführt, würde ein Siegelfehler sonst als 2xx quittiert und nur zurückgerollt. `siegel_vor_antwort` (globale Abhängigkeit mit
`scope="function"`) siegelt deshalb vor dem Senden; ein Fehler wird zum HTTP 500 (`test_siegel_fehler_liefert_http_500_...`).
Ausnahmen: Login-Fehlschlag und Abmeldung (eigene Transaktion bzw. best effort; Abmeldung darf nie scheitern).

**Nicht protokolliert:** Anmeldeversuche unbekannter Adressen (kein Mandant, sonst durch Internetrauschen füllbar), Lesezugriffe.

**IP-Adresse – Abwägung.** Nutzen: Missbrauchsaufklärung bei Anmeldung/Kontosicherheit. Kosten: personenbezogenes Datum in einem
unveränderbaren Speicher, der sich nicht löschen lässt. Entscheidung: IP nur bei Anmelde-/Kontosicherheitsaktionen
(`AKTIONEN_MIT_IP`), nur gekürzt (IPv4 /24, IPv6 /48). Rechtsgrundlage berechtigtes Interesse (Art. 6 Abs. 1 lit. f DSGVO, Sicherheit);
im Verzeichnis der Verarbeitungstätigkeiten zu nennen. Details-JSON: Werte zu Schlüsseln wie `passwort*`, `token*`, `secret*` werden maskiert.

**Kettenende.** Wer die letzten Einträge samt Siegeln abschneidet, erzeugt wieder eine gültige Kette. Gegenmaßnahme: Kettenkopf
(`kopf_seq`, `kopf_hash`) aus der Prüfung extern festhalten (Vollexport-Manifest enthält ihn).

## 2. Festschreibung

Trigger-Whitelist siehe Migration 0114. Erlaubt nach Versand: Status (nie zurück auf `entwurf`), `bezahlt_am`, `mahnstufe`,
`letzte_mahnung_am`, `geloescht_am/-von`, `updated_at`; einmalig NULL → Wert: `pdf_object_key`, `xml_object_key`, `pdf_sha256`,
`xml_sha256`, `e_rechnung_profil`, `leitweg_id`. Alles andere ist Kernfeld.

**Gleiche Transaktion.** Storno- und Gutschriftsbelege entstehen als `versendet` und werden danach noch befüllt (Betrag,
Positionen, Archiv). Der Trigger erlaubt Änderungen an Zeilen, deren `xmin` der laufenden Transaktion entspricht
(`OLD.xmin = pg_current_xact_id()::xid`). Grenze: Wurde eine alte Rechnung in derselben Transaktion bereits legitim geändert (z. B.
Status), ist sie ebenfalls „in dieser Transaktion berührt“; und Zeilen aus einem Savepoint haben ein abweichendes `xmin`
(nicht vorgesehen). Positionen: nur `UPDATE`/`DELETE` sind gesperrt, `INSERT` nicht – Testdaten und Importe legen Positionen zu versendeten Belegen an;
die API verbietet das ohnehin.

**Löschen.** `DELETE` nur mit Session-Variable `app.gobd_loeschfreigabe`, die `papierkorb_service.purge` nach der Fristprüfung setzt.

**Hashes.** `pdf_sha256`/`xml_sha256` beim Versand. Altbestand: `POST …/archiv-pruefung/hash-nachtragen` (beweist nur den Stand ab jetzt).

## 3. Aufbewahrung

Konstanten statt Tabelle (gesetzliche Fristen sind nicht mandantenspezifisch): `aufbewahrung_service`. Fristende = 31.12. des
Entstehungsjahres + Jahre. Entstehung in der Betriebszeitzone. Eingangsrechnung: `eingegangen_am`. Angebote (nach Versand) sind
Geschäftsbriefe (6 Jahre) und jetzt ebenfalls gesperrt – bisher waren sie es nicht. Löschvorschlagsliste ohne Automatik; Job zum
„Vormerken“ nicht umgesetzt (die Liste wird bei Abruf berechnet).

**DSGVO-Konflikt.** Es gibt kein Kunden-Anonymisieren (nur Mitarbeiter-Anonymisierung). Löschverlangen = Kunde in den Papierkorb
(Verarbeitung gesperrt); endgültiges Löschen verweigert mit Fristende (Art. 17 Abs. 3 lit. b DSGVO), auch wenn die Belege nicht im
Kaskadenbaum des Kunden hängen (`_pruefe_belege_des_kunden`). Nach Fristablauf: Admin legt Beleg in den Papierkorb (Vorschlag),
Papierkorb-Konto löscht Beleg, dann Kunde.

## 4. Objektspeicher

Neue Schlüssel: `mandanten/<mandant_id>/<bereich>/<id>/…`. Altobjekte bleiben unberührt; der Lesepfad nutzt den in der DB gespeicherten
Schlüssel und ist deshalb kompatibel. `key_gehoert_zu_mandant` liefert für Altschlüssel `None` (nicht entscheidbar). Aufräumen nach
dem Löschen: Aufträge in `s3_loeschauftraege` (gleiche Transaktion wie das DELETE), Ausführung nach dem Commit als Hintergrund-Task
und im Worker, Wiederholung mit Wartezeit, `fehler` nach 10 Versuchen. Löschen per Präfix (neues und altes Schema), alle Versionen;
Rückfall auf unversioniertes Löschen ohne `ListBucketVersions`.

## 5. Exporte

`mandant_exporte` (Teil-Unique-Index: ein wartender/laufender Export je Mandant). Verarbeitung nach dem Commit im API-Prozess,
Worker holt Liegengebliebenes (30 s) und entfernt Ergebnisse nach 7 Tagen. Streaming: ZIP auf Platte, Objekte in 1-MiB-Blöcken.
Daten nur über Mandanten-Session (RLS) plus Mandantenfilter, Objektschlüssel mit fremdem Präfix werden übersprungen. Rechte:
`nur_mandant_admin` (schließt das Papierkorb-Konto `loesch_operativ` aus, das sonst alle Admin-Rechte erbt).

## Offen

Siehe `docs/BACKLOG.md` Punkt 13.
