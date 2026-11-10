# Datenimport: Offene Posten (Entwurf, nicht umgesetzt)

Entscheidungsvorlage für den Product Owner. Ziel: Ausgangsrechnungen aus dem Altsystem, die
noch unbezahlt sind, sollen in FieldVibe überwacht (Zahlungseingang, Mahnung) werden, ohne
dass Umsatz oder Umsatzsteuer doppelt erscheinen.

## Warum nicht einfach als Rechnung importieren

Ein Import in `rechnungen` wirkt an vielen Stellen, die ihn nicht als Altlast erkennen:

* **UStVA/Auswertung** (`auswertung_service.ust_va_bericht`) und **DATEV-Export** nehmen alle
  Rechnungen mit `versendet_am` im Zeitraum, ohne Herkunftskennzeichen. Die Umsätze wurden aber
  im Altsystem bereits erklärt und gebucht (Doppelerfassung, falsche Voranmeldung).
* **Rechnungsnummer:** `rechnungen` hat nur `UNIQUE(mandant_id, rechnungsnummer)` und der
  Nummernkreis ist `R-nnnnn`; Fremdnummern kollidieren nicht technisch, aber GoBD verlangt eine
  lückenlose, eigene Nummernfolge für selbst erstellte Belege.
* **Mahnwesen** (`mahnwesen_service`) mahnt jede `versendet`/`teilweise_bezahlt`-Rechnung nach
  Fälligkeit automatisch per Mail an den Kunden; ein Importfehler (Datum, Betrag) löst reale
  Mahnungen aus.
* Rechnungen brauchen Positionen (Steuerkategorie je Position), erzeugen PDF/E-Rechnung und
  sind ab Versand GoBD-gesperrt (nicht löschbar): ein fehlerhafter Import ließe sich nicht
  mehr zurücknehmen.
* Das Rechnungsmodell kennt weder „Übernahme Altsystem“ noch einen Offene-Posten-Stand ohne
  Beleg. Deshalb wurde (d) nicht umgesetzt.

## Optionen

**A: Eigene Tabelle `offene_posten_altsystem`** (Empfehlung). Felder: Fremdnummer, Kunde,
Belegdatum, Fälligkeit, Brutto, Netto, Steuersatz, offener Betrag, Mahnstufe, Quelle/Lauf.
Kein Beleg, kein Umsatz: UStVA, DATEV und Erlöskonten bleiben unberührt. Zahlungseingänge
mindern den offenen Betrag, bei 0 gilt der Posten als erledigt. Eigene Ansicht in der
Debitorenübersicht, Mahnwesen optional und standardmäßig aus. Risiko: zweiter Datentopf in der
Forderungsübersicht (Summen müssen beide Quellen zeigen); DATEV-OP-Ausgleich bräuchte eine
Sonderbehandlung.

**B: Rechnung mit Kennzeichen `herkunft = 'altsystem'`.** Wiederverwendung von Zahlung, Liste,
Mahnwesen. Nötig: Migration, Ausschluss in UStVA (`auswertung_service`), DATEV und
Erlösstatistik, keine Positionen/PDF/E-Rechnung (Betragsfelder statt Positionen), eigener
Statusweg, Löschbarkeit trotz Versand, Nummernkreis unberührt. Risiko: jede künftige
Auswertung muss das Kennzeichen kennen; ein Vergessen verfälscht Steuerzahlen.

**C: Nur Mahnwesen-Merker am Kunden/als Notiz.** Kein Datenmodell, keine Überwachung, kein
Zahlungsabgleich. Für Betriebe mit wenigen offenen Posten ausreichend, sonst keine Lösung.

## Offene Fragen an den Product Owner

1. Reichen Forderungsüberwachung und Mahnung, oder werden Zahlungsbuchungen/DATEV-OP-
   Ausgleich für diese Posten gebraucht (spricht für B)?
2. Soll das Mahnwesen für Altposten automatisch laufen (Mail an Kunden aus FieldVibe heraus)?
3. Stichtag/Parallelbetrieb: Werden im Altsystem noch Rechnungen erzeugt, sodass sich Altposten
   und neue Belege überschneiden?
4. Abstimmung mit dem Steuerberater: Welche Posten gelten als „übernommen“, und wie wird die
   Eröffnungsbilanz der Forderungen abgeglichen?

## Vorschlag

Option A mit dem bestehenden Import-Assistenten als vierter Typ (Probelauf, Dubletten per
Fremdnummer + Kunde, Rückgängig), erst nach Klärung von Frage 1 und 2.
