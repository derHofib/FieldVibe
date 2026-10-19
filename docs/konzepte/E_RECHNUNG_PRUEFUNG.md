# E-Rechnung: Konformitätsprüfung (EN 16931)

Stand: 19.10.2026

Unsere ausgehende E-Rechnung (`e_invoice_service.baue_cii_dokument`, CII, Profil
`urn:cen.eu:en16931:2017` bzw. XRechnung 3.0, siehe `XRECHNUNG.md`) wird zusätzlich zur
XSD-Prüfung von drafthorse gegen die **CEN-Geschäftsregeln (Schematron)** und, bei
XRechnung-Dokumenten, gegen die **BR-DE-Regeln der KoSIT** geprüft. Die XSD allein findet
Rechenfehler und Regelverstöße wie BR-CO-10, BR-27 oder BR-Z-09 nicht.

## Ausführen

```bash
scripts/e-rechnung/installieren.sh                 # einmalig, lädt nach .cache/e-rechnung (gitignoriert)
scripts/e-rechnung/pruefen.sh [--svrl <dir>] datei.xml [...]
cd backend && pytest tests/test_e_rechnung_konformitaet.py
```

- `pruefen.sh` gibt je Datei `OK` oder `FEHLER` aus, bei Fehlern mit Regel-ID, Meldung und
  Fundstelle (XPath). Exit-Code 1 bei Regelverstößen, 2 bei fehlendem Werkzeug. Warnungen
  (Flag `warning`/`information`) werden angezeigt, zählen nicht als Fehler. Dokumente mit der
  XRechnung-Kennung (`…kosit:xrechnung_3.0`) laufen zusätzlich durch die BR-DE-Regeln. `--svrl` legt den rohen
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
| XRechnung-Regeln (BR-DE-*, `cii/XRechnung-CII-validation.sch` + `common.sch`) | Tag `v2.6.0` (kompatibel mit XRechnung 3.0), Commit `217c6cbf8ac9a99d780cefb4f044b2c2778d4744` | `itplr-kosit/xrechnung-schematron` (GitHub-Spiegel) |
| SchXslt (Schematron → XSLT 2.0) | 1.10.1 | Maven Central `name.dmaus.schxslt:schxslt` |

Aufruf intern: `java -cp saxon:xmlresolver net.sf.saxon.Transform -s:<xml> -xsl:<regeln.xslt>`
liefert SVRL; `svrl-auswertung.xsl` macht daraus die Ausgabe. Ein Dokument, auf das keine
Regel angewendet wurde (falsches Wurzelelement), gilt als Fehler.

Die XRechnung-Regeln kompiliert `installieren.sh` selbst (Saxon + SchXslt,
`xslt/2.0/pipeline-for-svrl.xsl`) aus den gepinnten Quelldateien; gepinnt sind deren SHA-256 und
das SchXslt-Jar. Das kompilierte XSLT ist nicht byte-stabil (generierte IDs) und deshalb nicht
gepinnt. `unzip` wird dafür gebraucht. Ältere Caches ohne `XRechnung-CII-validation.xslt` bleiben
für die EN-16931-Tests nutzbar; die XRechnung-Tests werden dann übersprungen
(`installieren.sh` erneut laufen lassen).

Versionen anheben: neue Werte und Prüfsummen in `pins.sh` eintragen (Prüfsummen der
Maven-Jars stehen als `.sha256` neben den Artefakten; die der XSLT mit `sha256sum` aus dem
gepinnten Commit bestimmen), danach die Konformitätstests laufen lassen.

### Warum nicht der KoSIT-Validator

Geprüft wurde `itplr-kosit/validator-configuration-xrechnung` (Stand 2026-09-04): Die
XRechnung-Szenarien greifen nur bei der XRechnung-CustomizationID; für reines EN 16931
(CII) gibt es ein eigenes Szenario, das **dieselbe** CEN-XSLT (`EN16931-CII-validation.xsl`)
verwendet, die hier direkt eingesetzt wird. Die Konfiguration entsteht erst per Ant-Build mit
Downloads von CEN-Release-URLs und dem XRechnung-Schematron-Paket (`projekte.kosit.org`,
aus der Sandbox nicht erreichbar), der Validator selbst ist ein GitHub-Release (ebenfalls nicht
erreichbar; auf Maven Central liegt nur die ältere Version 1.5.0). Die direkte Variante prüft
die gleichen Regeln mit weniger Beweglichem: CEN-Regeln plus die BR-DE-Regeln aus den
Schematron-Quellen von `xrechnung-schematron`, jeweils per Saxon.

**Nicht gelaufen ist der KoSIT-Validator selbst** (Prüfung der Pflicht-/Wiederholungsstruktur
über die XSD der Konfiguration, Prüfbericht, Szenario-Auswahl). Die Konformität ist damit „CEN-
und BR-DE-Schematron bestanden", nicht „KoSIT-Validator bestanden". Vor einer produktiven
Behörden-Rechnung einmal mit dem echten Validator (oder dem Prüfdienst der Empfänger-
Plattform) gegenprüfen.

## Was geprüft wird – und was nicht

Geprüft: alle Geschäftsregeln der EN 16931 (BR-*, BR-CO-*, BR-S/Z/E/AE-*, CII-DT-*, CII-SR-*)
in Version 1.3.17 auf der erzeugten CII-XML; bei XRechnung-Dokumenten zusätzlich die BR-DE-Regeln
(BR-DE-1 bis -31, BR-TMP-*) in Version 2.6.0. Die Tests decken Einzelsatz, Mischsatz,
alle Kategorien, Kleinunternehmer, Storno, Gutschrift, Abschlag und Schlussrechnung als
XRechnung ab und enthalten Negativkontrollen für BR-DE-1/2/6/7/8/15/23-a.

**Nicht** geprüft:

- Alles, was der KoSIT-Validator zusätzlich zu den Schematron-Regeln prüft (siehe oben), und
  die Peppol-/XRechnung-Erweiterungen (`BR-DEX-*`, nur für das Profil „Extension" relevant).
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

Beim ersten XRechnung-Lauf gefunden und behoben (beides Warnungen): BR-DE-17 (der Typcode 386
für Abschlagsrechnungen ist in der XRechnung nicht vorgesehen → dort 326, bei ZUGFeRD bleibt 386)
und BR-DE-26 (Storno-Beleg 384 soll die Ursprungsrechnung referenzieren → BT-25 bei XRechnung).

Typcode beim Storno: bleibt **384** (Rechnungskorrektur) mit negativen Beträgen. Die EN-16931-
Regeln akzeptieren 380, 381 und 384 gleichermaßen (die Storno-XML besteht mit allen drei Codes);
384 beschreibt eine Korrektur der Ursprungsrechnung am treffendsten. Ein Verweis auf die
Ursprungsrechnung (BT-25) wird bei ZUGFeRD nicht ausgegeben (die EN-16931-Regeln verlangen ihn nicht),
bei XRechnung schon (BR-DE-26).
