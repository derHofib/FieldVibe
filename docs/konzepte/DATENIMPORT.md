# Datenimport (CSV/XLSX-Assistent)

Roadmap 1.10: Ein Betrieb übernimmt Kunden, Anlagen und Material aus dem Altsystem ohne
Handarbeit. Backend `app/services/datenimport/`, API `/api/import`, Oberfläche
`frontend/src/office/datenimport/` (nur Office-Shell, Seite „Datenimport“ unter Verwaltung).
Offene Posten sind nicht umgesetzt, siehe `DATENIMPORT_OFFENE_POSTEN.md`.

## Ablauf

Zustandslos über den Server: Die Datei liegt zwischen den Schritten SSE-S3-verschlüsselt unter
`mandanten/<mandant>/datenimport/<lauf>/quelle-<uuid>.bin` (nie mit dem Dateinamen des Nutzers im
Key). Jeder Schritt liest sie neu.

1. `POST /api/import/analyse` (multipart `datei`, `entitaet`, optional `blatt`): erkennt
   Format, legt den Lauf (`import_laeufe`) an, liefert Spalten mit Beispielwerten,
   Zuordnungsvorschlag, Felder und Dublettenarten.
2. `POST /{id}/probelauf` mit Zuordnung + Optionen: prüft jede Zeile (neu | warnung | dublette |
   fehler), schreibt nichts, merkt sich Konfiguration und deren Hash.
3. `POST /{id}/ausfuehren` mit derselben Konfiguration: nur möglich nach einem Probelauf mit
   exakt dieser Konfiguration (409 sonst). Prüft erneut gegen den aktuellen Bestand und
   schreibt dasselbe, was der Probelauf gezeigt hat.
4. `GET /{id}`, `GET /` (Läufe), `GET /{id}/fehlerbericht.csv[?arten=fehler,dublette,warnung]`,
   `POST /{id}/rueckgaengig`, `DELETE /{id}` (Lauf verwerfen), `GET /vorlagen/<typ>.csv`.

Optionen: `modus` = `gueltige` (Standard: gültige Zeilen importieren, fehlerhafte als Bericht) oder
`alles_oder_nichts`; `chargengroesse` (Standard 200, 10–1000: je Charge ein eigener
Sicherungspunkt, schlägt der Datenbank-Insert fehl, wird die Charge zeilenweise wiederholt und nur
die schuldige Zeile als Fehler gezählt); `dubletten_aktionen` je Dublettenart
(`ueberspringen` | `aktualisieren` | `anlegen`, Standard überspringen).

## Formate

* CSV/TXT/TSV: Kodierung UTF-8, UTF-8 mit BOM, UTF-16 (BOM), sonst Windows-1252; Trennzeichen
  `;` `,` Tab `|` (oder Excel-Zeile `sep=;`) automatisch erkannt. Leere Zeilen und Spalten
  ohne Kopf/Inhalt entfallen.
* XLSX: erstes sichtbares oder gewähltes Blatt. Nur Lesen (`read_only`, `data_only`).
  Abgelehnt: `.xls`, `.xlsm`/`.xlsb`, Makros (`vbaProject.bin`), externe Verknüpfungen,
  XML mit `<!DOCTYPE`/`<!ENTITY`, entpackt > 100 MB (Zip-Bombe).
* Zahlen: `1.234,56`, `1234,56`, `1,234.56`, `1'234.50`, mit `€`/`EUR`. Excel-Zahlenzellen werden
  mit Typ gelesen (kein „1.234“-Missverständnis); Format `00000` stellt führende Nullen
  wieder her (PLZ, Kundennummer). Als Text gespeicherte Werte bleiben unverändert.
* Datum: `TT.MM.JJJJ`, `TT.MM.JJ`, `TT/MM/JJJJ`, `JJJJ-MM-TT`, `JJJJMMTT`, Excel-Seriennummern.
* Steuerzeichen, NUL, Zero-Width- und Bidi-Zeichen werden entfernt; ein führendes `'` vor
  `= + - @` (Formelschutz aus dem Fehlerbericht) wird beim erneuten Import wieder abgezogen.

## Limits (ENV `FIELDVIBE_IMPORT_*`)

10 MB, 20.000 Datenzeilen, 100 Spalten, 5.000 Zeichen je Zelle, 100 MB entpackt (XLSX),
60 s Zeitlimit (Parser und Verarbeitung; bei Überschreiten wird alles zurückgenommen, HTTP 408),
Quelldatei 24 h, Fehlerbericht 7 Tage. Aufräumen im stündlichen Worker-Tick
(`raeume_auf`); der Lauf selbst bleibt als Nachweis. Nach einem erfolgreichen Import wird die
Quelldatei sofort gelöscht. Das Body-Limit vor dem Endpunkt (Reverse-Proxy) ist nicht Teil der
App: dort empfiehlt sich ein Limit etwas über 10 MB.

## Entitäten und Synonyme

Die Zuordnung wird per Kopfzeilen-Synonymen vorgeschlagen (Umlaute, Groß-/Kleinschreibung und
Satzzeichen egal; exakte Treffer vor Teiltreffern; jede Spalte höchstens einem Feld). Die
Synonymlisten stehen in `felder.py`, z. B. Kundennummer: Kundennummer, KdNr, Kd-Nr, Kunden-Nr;
Name: Firma, Name, Kundenname; PLZ: PLZ, Postleitzahl; USt-IdNr: USt-IdNr, VAT ID …

**Kunden** (`KundeCreate`): Kundennummer (leer = automatisch), Name/Firma (oder Vorname +
Nachname), Typ (privat/gewerbe/oeffentlich/hausverwaltung mit Synonymen), Straße (+ Hausnummer),
PLZ, Ort, Ansprechpartner (Name, Position, E-Mail, Telefon/Mobil; E-Mail/Telefon ohne
Ansprechpartnername landen beim Firmennamen), USt-IdNr. (Formatwarnung, wird übernommen),
Leitweg-ID (Prüfziffer, Fehler), Debitorenkonto (Format + Bereich der Sachkontenlänge,
Duplikat → Fehler), Notiz.
Nummernkreis: eigene Nummern im Format `K-00123` heben den Zähler auf Maximum + 1; automatische
Nummern werden blockweise reserviert und kollidieren nie mit Bestand, Papierkorb oder Datei.
Fremde Formate (`10023`) bleiben unverändert und beeinflussen den Zähler nicht.
Dublettenarten (Reihenfolge = Vorrang): Kundennummer (nur überspringen/aktualisieren), USt-IdNr.,
Name + PLZ (nur mit PLZ auf beiden Seiten), E-Mail (beliebiger Ansprechpartner).

**Standorte & Anlagen:** Kunde über Kundennummer, sonst eindeutigen Kundennamen (unbekannt/
mehrdeutig → Fehler). Zeile mit Anlagenbezeichnung = Anlage; ohne = nur Standort. Standort wird
je Kunde per Bezeichnung gesucht oder einmalig angelegt; Adressspalten gelten für Standort und
Anlage. Baujahr: kein Feld im Modell, wird als Zeile „Baujahr: JJJJ“ in die Notiz geschrieben.
Prüfdaten: Prüfintervall (Monate) + letzte Prüfung (+ optional nächste Prüfung) ergeben einen
Prüfzyklus wie `POST /api/pruefzyklen` (ohne letzte Prüfung: ab heute). Ungültige Prüfdaten sind
ein Zeilenfehler; ohne Intervall oder bei deaktiviertem Modul „Prüfzyklen“ gibt es eine Warnung.
Dublettenarten: Seriennummer + Kunde, Bezeichnung + Standort, Standort (reine Standortzeile).
Keine Geokodierung beim Import.

**Material:** Artikelnummer, Bezeichnung (Pflicht), Einheit (Standard Stk), Einzelpreis (netto),
Mindestbestand, Anfangsbestand (Zentrallager, Bewegung „eingang“). Einkaufspreise kennt das
Modell nicht und werden nicht importiert. Dublette per Artikelnummer, ohne Artikelnummer per
Bezeichnung.

„Aktualisieren“ ergänzt ausschließlich leere Felder des vorhandenen Datensatzes. Eine Dublette
innerhalb derselben Datei lässt sich nie aktualisieren (wirkt wie überspringen).

## Rückgängig

`import_lauf_eintraege` hält die IDs der angelegten/aktualisierten Datensätze. „Rückgängig“ legt
angelegte Datensätze in den Papierkorb, wenn sie seit dem Import unverändert sind
(`updated_at = created_at`) und nichts Fremdes daran hängt (Aufträge, Rechnungen, Verträge,
Buchungen …). Blockierte werden gemeldet. Aktualisierte Datensätze werden nicht zurückgesetzt;
vergebene Nummern kommen nie zurück. Wiederherstellung einzelner Stücke über den Papierkorb.

## Rechte und Sicherheit

Nur `mandant_admin` (wie überall mit `loesch_operativ`); kein eigener Rechte-Bereich, weil ein
Import quer über Kunden, Anlagen und Material schreibt. Modul-Sperren (`kundenverwaltung`,
`material`) gelten. Mandantentrennung über RLS (`import_laeufe`, `import_lauf_eintraege`);
fremde Läufe sind 404. Dateiinhalt wird nie geloggt, Meldungen wiederholen keine Zellwerte,
Dateinamen dienen nur der Anzeige. Fehlerbericht: Formelschutz (Zellen mit `= + - @` bekommen ein
`'` vorangestellt). Audit-Log: `datenimport_ausgefuehrt`/`_abgebrochen`/`_rueckgaengig`.

## Grenzen

Kein Import von Vorgängen, Verträgen, Rechnungen/offenen Posten, Fotos; keine Anlagen-
Zusatzfelder (`stammdaten`); eine Datei = ein Typ; keine Ansprechpartnerlisten über mehrere
Spalten; synchron bis 20.000 Zeilen; Probelauf-Antwort zeigt je Status nur die ersten Zeilen
(vollständig im CSV-Bericht).
