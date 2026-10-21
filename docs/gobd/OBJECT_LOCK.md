# S3 Object Lock für archivierte Rechnungen (optional)

> **Status: UNGETESTET gegen echtes MinIO.** Die Logik ist gegen den S3-Mock `moto` geprüft
> (`tests/test_rechnung_festschreibung.py::test_object_lock_retention_bis_fristende_wenn_aktiviert`),
> der Docker-/MinIO-Betrieb konnte in der Entwicklungsumgebung nicht ausprobiert werden. Vor dem Einsatz
> auf einer Testinstanz verifizieren. **Standardmäßig aus; wird nirgends erzwungen.**

## Wozu

Die Datenbank schützt festgeschriebene Rechnungen per Trigger und hält den SHA-256 der archivierten Dateien.
Object Lock (WORM) schützt zusätzlich die **Dateien selbst** im Objektspeicher gegen Überschreiben und Löschen –
auch bei kompromittiertem Server oder Fehlbedienung – bis zum Ende der Aufbewahrungsfrist.

## Konfiguration

| Variable | Wirkung |
|---|---|
| `S3_OBJECT_LOCK=true` | Beim **Anlegen** des Buckets (`ensure_bucket`) wird Object Lock aktiviert (schaltet Versionierung ein). Ein bestehender Bucket wird nicht verändert. |
| `S3_RECHNUNGEN_RETENTION=off\|governance\|compliance` | Archiv-PDF/-XML einer Rechnung erhalten beim Hochladen eine Objekt-Aufbewahrung bis zum Fristende (31.12. des 8. Folgejahres, + 1 Tag). Standard `off`. |

- **Governance:** Löschen nur mit Sonderrecht (`s3:BypassGovernanceRetention`); ein Eingriff bleibt möglich und auditierbar.
- **Compliance:** niemand (auch der Root-Nutzer) kann vor Ablauf löschen oder die Frist verkürzen. **Nicht rücknehmbar** –
  nur einsetzen, wenn der Steuerberater das verlangt und die Fristberechnung (siehe unten) geprüft ist.

Es wird bewusst **nur pro Objekt** gesperrt (keine Bucket-Standard-Retention): Fotos, Exporte und Dokumente müssen für
Datenschutz-Löschungen und das Aufräumen nach dem endgültigen Löschen löschbar bleiben.

## Einrichtung MinIO (manuell)

1. Neuen Bucket **mit Lock** anlegen (bei MinIO nur bei der Erstellung möglich):
   `mc mb --with-lock fvroot/fieldvibe-fotos-lock`
2. Bestehende Objekte übernehmen: `mc mirror fvroot/fieldvibe-fotos fvroot/fieldvibe-fotos-lock`
   (Altobjekte behalten ihre Schlüssel; es gibt keine Umbenennung).
3. `S3_BUCKET_FOTOS=fieldvibe-fotos-lock`, `S3_OBJECT_LOCK=true`, `S3_RECHNUNGEN_RETENTION=governance` in der `.env`,
   `scripts/minio-service-account.sh` erneut ausführen (die Policy enthält jetzt `PutObjectRetention`, `GetObjectRetention`,
   `ListBucketVersions`, `DeleteObjectVersion`), Dienste neu starten.
4. Prüfen: Rechnung versenden, dann `mc stat --versions fvroot/<bucket>/<key>` zeigt Retention-Modus und Datum.
5. Variablen müssen in `docker-compose.yml` an Backend **und** Worker durchgereicht sein (Abschnitt `environment`).

## Zusammenspiel mit dem Löschen

Nach Fristablauf löscht das Aufräumen nach dem endgültigen Löschen alle **Versionen** der Objekte (`delete_prefix`). Läuft die
Retention noch (z. B. Fristende in der Datenbank anders berechnet als beim Upload), schlägt das Löschen fehl; der Auftrag bleibt
in der Retry-Liste (`GET /api/aufbewahrung/s3-loeschauftraege`) und wird später erneut versucht.

## Grenzen

- Die Retention wird mit dem **Fristende zum Versandzeitpunkt** gesetzt. Ändert sich die Rechtslage (kürzere/längere Frist),
  gilt für bereits gesperrte Objekte die alte Dauer; eine Verlängerung wäre ein eigener Lauf (nicht umgesetzt).
- Alt-Rechnungen (vor Aktivierung archiviert) sind nicht gesperrt.
- Backups (Abschnitt 5 der Betriebsdoku) liegen außerhalb des Locks.
