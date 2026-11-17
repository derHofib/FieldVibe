import { describe, expect, it } from "vitest";

import {
  kachelAuswahlAusSpeicher,
  kachelAuswahlFuerSpeicher,
  kachelUmschalten,
  sichtbareKacheln,
  standardKacheln,
} from "./arbeitszeitKacheln";

describe("arbeitszeitKacheln", () => {
  it("liefert ohne Speicherstand den Default", () => {
    expect(kachelAuswahlAusSpeicher(null)).toEqual(standardKacheln());
    expect(standardKacheln().has("jahr")).toBe(false);
    expect(standardKacheln().has("saldo_monat")).toBe(true);
  });

  it("faellt bei kaputtem JSON oder falschem Typ auf den Default zurueck", () => {
    expect(kachelAuswahlAusSpeicher("{")).toEqual(standardKacheln());
    expect(kachelAuswahlAusSpeicher('{"a":1}')).toEqual(standardKacheln());
  });

  it("verwirft unbekannte IDs und behaelt ein leeres Array als 'alles aus'", () => {
    expect([...kachelAuswahlAusSpeicher('["jahr","gibtsnicht",3]')]).toEqual(["jahr"]);
    expect(kachelAuswahlAusSpeicher("[]").size).toBe(0);
  });

  it("serialisiert in fester Reihenfolge und liest wieder ein", () => {
    const s = kachelAuswahlFuerSpeicher(new Set(["jahr", "ist_monat"] as const));
    expect(s).toBe('["ist_monat","jahr"]');
    expect(kachelAuswahlAusSpeicher(s)).toEqual(new Set(["ist_monat", "jahr"]));
  });

  it("schaltet einzelne Kacheln um, ohne das Original zu veraendern", () => {
    const start = standardKacheln();
    const aus = kachelUmschalten(start, "woche");
    expect(aus.has("woche")).toBe(false);
    expect(start.has("woche")).toBe(true);
    expect(kachelUmschalten(aus, "woche").has("woche")).toBe(true);
  });

  it("sortiert sichtbare Kacheln nach Registry und beachtet Verfuegbarkeit", () => {
    const auswahl = new Set(["urlaub_verbleibend", "saldo_monat", "ist_monat"] as const);
    expect(sichtbareKacheln(auswahl, new Set(["urlaub_verbleibend", "saldo_monat", "ist_monat"]))).toEqual([
      "ist_monat",
      "saldo_monat",
      "urlaub_verbleibend",
    ]);
    expect(sichtbareKacheln(auswahl, new Set(["ist_monat"]))).toEqual(["ist_monat"]);
  });
});
