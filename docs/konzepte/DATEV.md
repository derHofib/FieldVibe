# DATEV-Export (Buchungsstapel)

Stand: 19.10.2026

`GET /api/auswertung/datev-export?von=…&bis=…` erzeugt einen Buchungsstapel im DATEV-Format
(EXTF, Versionsnummer 700, Formatversion 13) aus versendeten Ausgangsrechnungen und nicht
stornierten Eingangsrechnungen. Code: `backend/app/services/datev_service.py` (Format,
Stammdaten, Kontenvergabe) und `auswertung_service.datev_export_csv`.

**Nicht gegen die DATEV-Spezifikation geprüft.** Header-Aufbau, Spaltenköpfe, Feldlängen und
Quoting sind aus dem Gedächtnis rekonstruiert (kein Zugriff auf die DATEV-Developer-Doku).
Vor dem ersten produktiven Einsatz ist ein Testimport beim Steuerberater Pflicht.

## Einrichtung je Mandant

Einstellungen ➝ Integrationen ➝ „DATEV / Buchhaltung“ (nur Mandant-Admin), gespeichert in
`Mandant.firmendaten["buchhaltung"]`:

| Feld | Bereich | Default |
|---|---|---|
| `berater_nr` | 1001–9999999 | – (Pflicht) |
| `mandant_nr` | 1–99999 | – (Pflicht) |
| `wirtschaftsjahr_beginn_monat` | 1–12 | 1 |
| `kontenrahmen` | `SKR03` / `SKR04` | `SKR03` |
| `sachkontenlaenge` | 4–8 | 4 |

Ohne Berater- und Mandantennummer antwortet der Export mit 422 („DATEV-Stammdaten
unvollständig …“); die Auswertungsseite zeigt das mit Link zu den Einstellungen. Es gibt
bewusst keinen Default, ein geratener Wert würde den Stapel beim falschen Mandanten landen
lassen. `buchhaltung` wird beim Speichern als Ganzes ersetzt (Erlöskonten und DATEV-Felder
müssen im selben PATCH stehen; die Oberfläche sendet beides).

Die Erlöskonten je Steuergruppe (`erloeskonten`, unverändert) müssen genau
`sachkontenlaenge` Stellen haben, sonst 422. Standardkonten ohne Eintrag (4-stellig, rechts
mit Nullen auf die Sachkontenlänge aufgefüllt):

| | SKR03 | SKR04 (aus dem Gedächtnis) |
|---|---|---|
| Erlös 19 % / 7 % | 8400 / 8300 | 4400 / 4300 |
| Kleinunternehmer | 8400 | 4400 |
| Aufwand wareneinkauf / betriebskosten / miete / personal / fahrzeug / versicherung / sonstiges | 3200 / 4900 / 4210 / 4120 / 4530 / 4360 / 4900 | 5200 / 6300 / 6310 / 6020 / 6530 / 6400 / 6300 |

## Personenkonten

Personenkonten haben Sachkontenlänge + 1 Stellen. Debitoren: `10^SL` bis `7·10^SL − 1`
(SL 4: 10000–69999), Kreditoren darüber (SL 4: 70000–99999).

- `kunden.debitorenkonto`, `lieferanten.kreditorenkonto`: je Mandant eindeutig, wenn gesetzt
  (Migration 0110, Teil-UNIQUE-Index; auch Papierkorb-Zeilen behalten ihr Konto).
- Manuell setzbar (Kundenprofil bzw. API); Verstöße gegen Länge/Bereich → 422, Duplikat → 409.
- Fehlt das Konto beim Export, wird es einmalig vergeben und bleibt stabil: bei Kunden die
  numerische Kundennummer, wenn sie genau SL+1 Stellen hat, im Bereich liegt und frei ist
  (Wünsche zuerst); sonst die kleinste freie Nummer ab Bereichsanfang. Sperrsicher über einen
  Advisory-Lock je Mandant und Art plus den UNIQUE-Index (Wiederholung bei Konflikt).
- Eingangsrechnungen ohne Lieferantenstamm (Freitext-Lieferant) buchen auf das Sammelkonto
  `7·10^SL` (SL 4: 70000), das nie an einen Lieferanten vergeben wird.
- Änderung der Sachkontenlänge: bereits vergebene Personenkonten behalten ihre Länge und
  müssen von Hand angepasst werden; es gibt keine Umnummerierung.
- Die früheren, aus `crc32(ID)` abgeleiteten Konten waren nie gespeichert und werden nicht
  rückwirkend nachgebildet.

## Format und Annahmen (aus dem Gedächtnis)

- Zeile 1 Header, Zeile 2 Spaltenköpfe, ab Zeile 3 Buchungen; Kodierung CP1252, Zeilenende
  CRLF, Trennzeichen `;`, Texte in `"…"` (Anführungszeichen verdoppelt), Zahlen/Daten
  unquotiert. Zeichen außerhalb CP1252: Akzentbuchstaben auf den Grundbuchstaben
  (`ő` → `o`), alles andere und Steuerzeichen → `?` bzw. Leerzeichen. Der Export bricht nie ab.
- Header, 31 Felder: 1 `"EXTF"`, 2 `700`, 3 `21`, 4 `"Buchungsstapel"`, 5 `13`,
  6 erzeugt am `YYYYMMDDHHMMSSfff` (UTC), 7 importiert (leer), 8 Herkunft `"FV"`,
  9 exportiert von `"FieldVibe"`, 10 importiert von (leer), 11 Berater, 12 Mandant,
  13 WJ-Beginn (1. des Beginnmonats im Jahr, das `von` enthält), 14 Sachkontenlänge,
  15/16 Datum von/bis (Exportzeitraum), 17 Bezeichnung (≤ 30), 18 Diktatkürzel (leer),
  19 Buchungstyp `1`, 20 Rechnungslegungszweck `0`, 21 Festschreibung `0` (nie festschreiben),
  22 WKZ `"EUR"`, 23–26 leer/reserviert (24 `""`), 27 SKR (`"03"`/`"04"`), 28–31 leer.
- Spalten 1–14: Umsatz, Soll/Haben, WKZ Umsatz, Kurs, Basis-Umsatz, WKZ Basis-Umsatz, Konto,
  Gegenkonto, BU-Schlüssel, Belegdatum (TTMM), Belegfeld 1 (≤ 36, Rechnungsnummer),
  Belegfeld 2, Skonto, Buchungstext (≤ 60, abgeschnitten). Weitere Spalten werden nicht
  ausgegeben (DATEV erlaubt das Weglassen hinterer Felder – Annahme).
- Belegfeld 1 wird nicht auf die von DATEV erlaubten Zeichen gefiltert (Annahme: Buchstaben,
  Ziffern und `$ & % * + - /`).
- Das Belegdatum ist TTMM ohne Jahr; DATEV ordnet es über Datum von/bis und
  Wirtschaftsjahr zu. Zeiträume über mehr als ein Wirtschaftsjahr sind daher mehrdeutig und
  werden nicht geprüft.
- Soll/Haben: Storno und Gutschrift sind Gegenbuchungen (`H`), siehe
  `tests/test_datev_soll_haben.py`.

## Nicht Teil dieses Stands

Zahlungsbuchungen (OP-Ausgleich) und gemischte MwSt-Sätze auf Eingangsrechnungen, siehe
`docs/BACKLOG.md`.
