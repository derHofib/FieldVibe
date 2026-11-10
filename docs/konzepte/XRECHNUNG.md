# XRechnung, E-Rechnung-Modus und Hinweise für Privatkunden

Stand: 19.10.2026 · Migration 0109 · Code: `e_invoice_service`, `privatkunden_service`,
`leitweg_id`, `rechnung_service` (Versandpfad)

## Was ein Kunde ist: „gewerblich“ und „privat“

Ein einziges Kriterium, `Kunde.ist_gewerblich`: Typ `gewerbe`, `oeffentlich` oder
`hausverwaltung`, **oder** eine USt-IdNr., **oder** eine Leitweg-ID. Alles andere (Typ `privat`,
Typ leer ohne diese Angaben) ist ein Privatkunde. Dasselbe Kriterium steuert den E-Rechnung-
Modus „b2b“ und die Hinweise nach § 14 Abs. 4 Nr. 9 UStG. Hausverwaltungen zählen als
gewerblich, weil sie beruflich für fremdes Eigentum abrechnen (offen: Rechnung an eine WEG,
siehe Fragen an den Product Owner im Bericht).

## E-Rechnung-Modus je Mandant

`firmendaten.e_rechnung_modus` ∈ `aus` | `b2b` | `alle`:

| Modus | E-Rechnung wird erzeugt für |
|---|---|
| `aus` | nie (normales PDF) |
| `b2b` | gewerbliche Kunden (Standard bei neuen Mandanten) |
| `alle` | alle Kunden |

Greift die E-Rechnung für einen Kunden, ist die Versandprüfung strikt: fehlende Pflichtangaben
liefern 422 mit Liste, kein stiller Fallback aufs PDF (bei Storno/Gutschrift bleibt der Fallback,
damit ein versendetes Original seine Korrektur nicht blockiert). Greift sie nicht, entsteht das
normale PDF.

`e_rechnung_aktiv` bleibt als abgeleiteter Wert erhalten (`modus != aus`). Fehlt der Modus
(Altdaten, direkt angelegte Mandanten), gilt `e_rechnung_aktiv` true → `alle`, sonst `aus`
(`e_invoice_service.e_rechnung_modus`); Migration 0109 schreibt das einmalig in alle Mandanten.
Die Einstellungs-API hält beide Schlüssel konsistent (der Modus gewinnt, ein älterer Client mit
nur `e_rechnung_aktiv` setzt den Modus mit).

## Profil: ZUGFeRD oder XRechnung

`Kunde.e_rechnung_format` (`zugferd` | `xrechnung` | leer = Automatik) und `Kunde.leitweg_id`.

- Automatik: Leitweg-ID gesetzt → XRechnung, sonst ZUGFeRD (EN 16931).
- `zugferd` mit Leitweg-ID: ZUGFeRD, die Leitweg-ID steht trotzdem als Käuferreferenz (BT-10).
- `xrechnung` ohne Leitweg-ID: Versand wird abgelehnt (BT-10 / BR-DE-15 ist Pflicht). Ein
  eigenes Feld für eine allgemeine Käuferreferenz gibt es nicht.

Beim Versand werden `rechnungen.e_rechnung_profil` (`en16931` | `xrechnung`) und
`rechnungen.leitweg_id` festgehalten (GoBD: spätere Änderungen am Kunden deuten den versendeten
Beleg nicht um). Beide sind NULL bei Entwürfen und Belegen ohne E-Rechnung.

### Leitweg-ID

`Grobadressierung (2–12 Ziffern) [- Feinadressierung (1–30 Buchstaben/Ziffern)] - Prüfziffer
(2 Ziffern)`, Eingabe wird getrimmt und in Großbuchstaben gespeichert. Die Prüfziffer ist
ISO 7064 MOD 97-10 über Grob- und Feinadressierung ohne Trennstriche (`98 − ((Zahl·100) mod 97)`,
Buchstaben A=10 … Z=35). Nachgerechnet mit den Beispielen `991-12345-73` und
`04011000-1234512345-06`. **Nicht verifiziert** ist die Buchstabenumwandlung (kein Beispiel mit
Buchstaben, die Spezifikation war nicht abrufbar) – siehe Kommentar in `leitweg_id.py`. Fehler
liefern 422 mit verständlicher Meldung (Format bzw. Prüfziffer).

### Zusätzliche Angaben für die XRechnung (BR-DE-*)

`pruefe_xrechnung_zusatz` (Teil der Versandprüfung, 422 mit Liste):

- Leitweg-ID des Kunden (BR-DE-15),
- Verkäufer-Kontakt BG-6 (BR-DE-2/5/6/7): Telefon (mind. drei Ziffern) und E-Mail aus den
  Firmendaten; als Kontaktname (BT-41) dient die Geschäftsführung, sonst der Firmenname als
  Abteilung,
- Zahlungsangaben BG-16/17 (BR-DE-1/23): IBAN der Firmendaten (Prüfsumme wird geprüft), BIC
  optional; Zahlungsart ist immer SEPA-Überweisung (58),
- Anschriften (BR-DE-3/4/8/9) und Steuerkennung (BR-DE-16) deckt die EN-16931-Prüfung ab.

Zusätzlich im Dokument: Kennung `urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`
(seit XRechnung 3.0 `xeinkauf.de`, nicht mehr `xoev-de:kosit:standard` wie in 2.x), BT-34
(Verkäufer-E-Mail, Schema `EM`) und BT-49 (Leitweg-ID, Schema `0204`) als elektronische Adressen,
Typcode 326 statt 386 für Abschläge (BR-DE-17), Verweis auf die Ursprungsrechnung beim Storno
(BR-DE-26). Eine Behörde (`oeffentlich`) braucht bei XRechnung keine USt-IdNr. mehr; bei ZUGFeRD
bleibt sie Pflicht.

### Versandweg bei XRechnung

Die XML ist die Rechnung. Beim Versand entstehen weiterhin ein **Hybrid-PDF** (PDF/A-3 mit
eingebetteter XML, XMP-Profil `XRECHNUNG`) und die einzeln archivierte XML (`xml_object_key`).
Begründung: Das PDF bleibt die menschenlesbare Fassung für Büro und Kundenportal und ist durch
die Einbettung dieselbe Rechnung wie die XML, nicht ein zweiter Beleg (kein doppelter
Steuerausweis nach § 14c UStG). Empfänger wie Eingangsportale der Verwaltung verarbeiten aber die
XML, nicht das PDF – deshalb hängt `POST /rechnungen/{id}/email` bei XRechnung zusätzlich
`<Rechnungsnummer>-xrechnung.xml` an, und `GET /rechnungen/{id}/xml` liefert sie unter diesem
Namen (ZUGFeRD: `factur-x.xml`). Den Abruf der empfangenen XML gibt es bereits
(`GET /eingangsrechnungen/{id}/xml-url`).

Das Kundenportal erzeugt sein PDF weiterhin live und bietet keinen XML-Download an.

### Prüfstatus

Angezeigt wird nur, dass die **interne Pflichtfeldprüfung bestanden** wurde (Profil
`e_rechnung_profil` am Beleg). Der Schematron-Lauf braucht Java und läuft nicht im
Produktions-Image; es gibt bewusst keinen eigenen Prüfstatus-Mechanismus. Die Konformität der
erzeugten XML belegen die Tests (`E_RECHNUNG_PRUEFUNG.md`).

## Hinweise für Privatkunden (§ 14 Abs. 4 Nr. 9 UStG, § 35a EStG)

Schalter `firmendaten.privatkunden_hinweise` (Standard an, nur `false` schaltet ab). Die
Texte kommen aus `privatkunden_service` und stehen identisch im PDF (Absätze unter dem
Summenblock) und als Rechnungsvermerke (BT-22) in der E-Rechnung.

| Rechnungsart | Aufbewahrungshinweis | Arbeitskosten (§ 35a) |
|---|---|---|
| Rechnung | ja | ja, wenn zuordenbar |
| Abschlag | ja | nein (keine Zuordnung von Arbeit/Material) |
| Schlussrechnung | ja | nein (Abzugszeilen der Abschläge) |
| Gutschrift, Storno | nein (korrigieren eine Rechnung, die den Hinweis trägt) | nein |

Aufbewahrungshinweis: Privatpersonen müssen die Rechnung zwei Jahre aufbewahren, beginnend mit
Ablauf des Kalenderjahres der Rechnungsstellung (§ 14b Abs. 1 Satz 5 UStG).

Arbeitskosten „Davon Arbeitskosten inkl. Fahrt- und Maschinenkosten“ (netto, Umsatzsteuer,
brutto; bei Kleinunternehmern nur der Betrag): ausgewiesen wird nur bei verlässlicher Zuordnung.
Arbeit sind Positionen mit der Quelle `zeit`, `fahrzeit`, `fahrtkosten`, Material solche mit
`material`. Enthält die Rechnung auch nur eine Position mit Quelle `leistung`
(Leistungsverzeichnis kann Lohn und Material mischen) oder ohne Quelle (manuell), wird **nichts
geraten** und nur der Aufbewahrungshinweis ausgegeben. Daraus folgt: in der Praxis erreichen
den Ausweis vor allem Rechnungen, die rein aus Zeiterfassung und Material übernommen wurden.

Fehlende Zuordnung – Vorschlag: Positionsflag `rechnung_positionen.ist_arbeitsleistung`
(Boolean, NULL = unbekannt), in der Positionsbearbeitung setzbar und bei Übernahme aus
Leistungsverzeichnis (Lohnanteil) und Zeiterfassung vorbelegt. Ein mischender LV-Eintrag
bräuchte außerdem die Aufteilung in Lohn-/Materialanteil je Position.

Zahlungshinweis: Wird der Arbeitskostenausweis gedruckt und sind Zahlungsangaben (IBAN)
hinterlegt, erscheint zusätzlich der Hinweis, dass die Steuerermäßigung eine unbare Zahlung
voraussetzt.
