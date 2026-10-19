# E-Rechnung: Konformitätsprüfung (EN 16931)

Stand: 19.10.2026

Unsere ausgehende E-Rechnung (`e_invoice_service.baue_cii_dokument`, CII, Profil
`urn:cen.eu:en16931:2017`) wird zusätzlich zur XSD-Prüfung von drafthorse gegen die
**CEN-Geschäftsregeln (Schematron)** geprüft. Die XSD allein findet Rechenfehler und
Regelverstöße wie BR-CO-10, BR-27 oder BR-Z-09 nicht.

## Ausführen

```bash
scripts/e-rechnung/installieren.sh                 # einmalig, lädt nach .cache/e-rechnung (gitignoriert)
scripts/e-rechnung/pruefen.sh [--svrl <dir>] datei.xml [...]
cd backend && pytest tests/test_e_rechnung_konformitaet.py
```

- `pruefen.sh` gibt je Datei `OK` oder `FEHLER` aus, bei Fehlern mit Regel-ID, Meldung und
  Fundstelle (XPath). Exit-Code 1 bei Regelverstößen, 2 bei fehlendem Werkzeug. Warnungen
  (Flag `warning`) werden angezeigt, zählen nicht als Fehler. `--svrl` legt den rohen
  SVRL-Bericht ab.
- Voraussetzungen: Java (>= 11), curl, git. Cache-Verzeichnis überschreibbar mit
  `EN16931_CACHE_DIR`.
- Die Konformitätstests erzeugen die XML über die echte Pipeline (Versand/Storno per API) für
  Einzelsatz, Mischsatz, Z, E, AE, alle Kategorien gemischt, Kleinunternehmer, Storno (auch
  mit allen Kategorien und Rundung), Rundungsrandfälle, mit/ohne Fälligkeit, ohne Positionen,
  private/öffentliche Kunden und eine Negativkontrolle (absichtlich verletzte BR-Z-10).
  Ohne installiertes Werkzeug werden sie übersprungen (Job `backend-tests`).
  `E_RECHNUNG_XML_DIR=<dir>` legt die erzeugten XML zur Fehlersuche ab.
- **CI:** Job `e-rechnung-konformitaet` in `.github/workflows/ci.yml` installiert das Werkzeug
  und lässt die Tests laufen; Überspringen macht den Job rot. Es sind keine Release-Downloads
  nötig: alles kommt aus Maven Central und einem `git fetch` auf einen gepinnten Commit.

## Wie die Prüfung funktioniert (Quellen und Pins)

Die Pins stehen in `scripts/e-rechnung/pins.sh`; `installieren.sh` bricht bei jeder
SHA-256-Abweichung ab und legt dann nichts im Cache ab.

| Baustein | Version | Quelle |
|---|---|---|
| Saxon-HE (XSLT-2.0-Prozessor) | 12.9 | Maven Central `net.sf.saxon:Saxon-HE` |
| xmlresolver (+ `data`-Jar, von Saxon 12 benötigt) | 5.3.3 | Maven Central `org.xmlresolver:xmlresolver` |
| Kompilierte EN-16931-Regeln für CII (`cii/xslt/EN16931-CII-validation.xslt`) | Release `validation-1.3.17` (2026-10-09), Commit `6e35e0ab8b09eb183f7d84b282e24ef95f9f5715` | `ConnectingEurope/eInvoicing-EN16931` |

Aufruf intern: `java -cp saxon:xmlresolver net.sf.saxon.Transform -s:<xml> -xsl:<regeln.xslt>`
liefert SVRL; `svrl-auswertung.xsl` macht daraus die Ausgabe. Ein Dokument, auf das keine
Regel angewendet wurde (falsches Wurzelelement), gilt als Fehler.

Versionen anheben: neue Werte und Prüfsummen in `pins.sh` eintragen (Prüfsummen der
Maven-Jars stehen als `.sha256` neben den Artefakten; die der XSLT mit `sha256sum` aus dem
gepinnten Commit bestimmen), danach die Konformitätstests laufen lassen.

### Warum nicht der KoSIT-Validator

Geprüft wurde `itplr-kosit/validator-configuration-xrechnung` (Stand 2026-09-04): Die
XRechnung-Szenarien greifen nur bei der XRechnung-CustomizationID; für reines EN 16931
(CII) gibt es ein eigenes Szenario, das **dieselbe** CEN-XSLT (`EN16931-CII-validation.xsl`)
verwendet, die hier direkt eingesetzt wird. Die Konfiguration entsteht erst per Ant-Build mit
Downloads von CEN-Release-URLs, der Validator selbst ist ein GitHub-Release (aus der Sandbox
nicht erreichbar; auf Maven Central liegt nur die ältere Version 1.5.0). Die direkte Variante
prüft die gleichen Regeln mit weniger Beweglichem.

## Was geprüft wird – und was nicht

Geprüft: alle Geschäftsregeln der EN 16931 (BR-*, BR-CO-*, BR-S/Z/E/AE-*, CII-DT-*, CII-SR-*)
in Version 1.3.17 auf der erzeugten CII-XML.

**Nicht** geprüft:

- **XRechnung** (CIUS): `BR-DE-*`-Regeln, Leitweg-ID, Pflichtkontakt des Verkäufers (BT-41/42/43),
  Zahlungsangaben. Dafür bräuchte es zusätzlich Profil, Daten und die XRechnung-Regeln.
- **Peppol BIS** (PEPPOL-EN16931-*, z. B. R120 zur Zeilensumme).
- Das **PDF/A-3-Hybrid** selbst (Einbettung, XMP) – nur die eingebettete XML.
- Fachliche Richtigkeit (richtiger Steuersatz, richtiger Befreiungsgrund): Die Regeln prüfen
  Konsistenz, nicht ob die Steuer korrekt gewählt wurde.

## Beim ersten Lauf gefundene und behobene Verstöße

| Regel | Befund | Behebung |
|---|---|---|
| CII-DT-031 | `currencyID` am Gesamtbetrag (BT-112) | nur noch am Steuerbetrag (BT-110) |
| BR-CO-26 | Verkäufer nur mit Steuernummer hatte weder BT-29, BT-30 noch BT-31 | Steuernummer zusätzlich als Verkäuferkennung (BT-29) – fachlich zu bestätigen |
| BR-CO-10, BR-S-08 | Zeilen banker-gerundet, Gruppennetto aus ungerundeter Summe | Zeilen kaufmännisch gerundet, BT-106 = Summe der Zeilen, Restdifferenz als Zu-/Abschlag „Rundungsdifferenz“ in der Steuergruppe |
| BR-27 | Storno-Zeilen mit negativem Nettopreis | Vorzeichen wandert in die Menge |
| BR-Z-09, BR-E-09, BR-AE-09 | Storno-Gruppen mit Steuerbetrag `-0.00` | Beträge werden normiert |

Typcode beim Storno: bleibt **384** (Rechnungskorrektur) mit negativen Beträgen. Die EN-16931-
Regeln akzeptieren 380, 381 und 384 gleichermaßen (die Storno-XML besteht mit allen drei Codes);
384 beschreibt eine Korrektur der Ursprungsrechnung am treffendsten. Ein Verweis auf die
Ursprungsrechnung (BT-25) wird nicht ausgegeben und von den Regeln nicht verlangt.
