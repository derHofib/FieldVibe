import { describe, expect, it } from "vitest";

import type { Rechnung, RechnungPosition } from "../types";
import {
  abschlagNettoAusProzent,
  abschlagPayload,
  abschlagVorschau,
  centZuText,
  gutschriftGrundFehler,
  gutschriftMengeFehler,
  gutschriftPayload,
  gutschriftSumme,
  kannGutschriftErstellen,
  maxGutschriftMenge,
  offenAnzeige,
  offenLabel,
  parseMenge,
  restMenge,
  rechnungsartVon,
} from "./rechnungsart";

function position(teil: Partial<RechnungPosition> = {}): RechnungPosition {
  return {
    id: "p1",
    position: 1,
    beschreibung: "Leitung",
    menge: "10.00",
    einheit: "m",
    einzelpreis: "10.00",
    gesamt: "100.00",
    ...teil,
  } as RechnungPosition;
}

describe("abschlagNettoAusProzent", () => {
  it("rundet kaufmännisch auf den Cent (ab .5 auf)", () => {
    // 33,33 % von 100,50 = 33,496650 -> 33,50
    expect(abschlagNettoAusProzent("100.50", "33.33")).toBe("33.50");
    // 12,5 % von 0,10 = 0,0125 -> 0,01; 50 % von 0,01 = 0,005 -> 0,01 (HALF_UP, nicht Bankers)
    expect(abschlagNettoAusProzent("0.10", "12.5")).toBe("0.01");
    expect(abschlagNettoAusProzent("0.01", "50")).toBe("0.01");
    expect(abschlagNettoAusProzent("0.01", "49.9")).toBe("0.00");
  });

  it("akzeptiert Dezimalkomma und liefert null bei Unsinn", () => {
    expect(abschlagNettoAusProzent("1000.00", "30,5")).toBe("305.00");
    expect(abschlagNettoAusProzent("1000.00", "abc")).toBeNull();
    expect(abschlagNettoAusProzent("", "10")).toBeNull();
  });

  it("vermeidet Float-Fehler (1.005-Fall)", () => {
    // 100,5 % von 1,00 = 1,005 -> Float würde 1.00 liefern, HALF_UP gibt 1.01
    expect(abschlagNettoAusProzent("1.00", "100.5")).toBe("1.01");
  });
});

describe("abschlagVorschau", () => {
  it("zeigt Betrag und Rest für Prozent", () => {
    const v = abschlagVorschau("prozent", "30", "1000.00", "1000.00");
    expect(v).toEqual({ betrag: "300.00", restNachher: "700.00", fehler: null });
  });

  it("zeigt Betrag und Rest für Nettobetrag", () => {
    const v = abschlagVorschau("netto", "250,555", "1000.00", "600.00");
    expect(v.betrag).toBe("250.56");
    expect(v.restNachher).toBe("349.44");
  });

  it("leere Eingabe ist kein Fehler, aber ohne Vorschau", () => {
    expect(abschlagVorschau("prozent", "  ", "1000.00", "1000.00")).toEqual({
      betrag: null,
      restNachher: null,
      fehler: null,
    });
  });

  it("lehnt 0, negative und über 100 % ab", () => {
    expect(abschlagVorschau("prozent", "0", "1000.00", "1000.00").fehler).toMatch(/größer als 0/);
    expect(abschlagVorschau("netto", "-5", "1000.00", "1000.00").fehler).toMatch(/größer als 0/);
    expect(abschlagVorschau("prozent", "100.01", "1000.00", "1000.00").fehler).toMatch(/höchstens 100 %/);
    expect(abschlagVorschau("prozent", "100", "1000.00", "1000.00").fehler).toBeNull();
  });

  it("lehnt Beträge über dem Rest ab und nennt den Rest", () => {
    const v = abschlagVorschau("netto", "400.01", "1000.00", "400.00");
    expect(v.fehler).toMatch(/mehr als 100 %/);
    expect(v.fehler).toMatch(/400,00/);
    expect(v.restNachher).toBe("-0.01");
    expect(abschlagVorschau("netto", "400.00", "1000.00", "400.00").fehler).toBeNull();
  });

  it("Prozent, das auf 0 Cent rundet, wird abgelehnt", () => {
    expect(abschlagVorschau("prozent", "0.001", "10.00", "10.00").fehler).toMatch(/größer als 0/);
  });
});

describe("abschlagPayload", () => {
  it("sendet genau eines von prozent/netto, Komma wird zum Punkt", () => {
    expect(abschlagPayload("a1", "prozent", " 30,5 ", "")).toEqual({
      angebot_id: "a1",
      rechnungsart: "abschlag",
      abschlag_prozent: "30.5",
    });
    expect(abschlagPayload("a1", "netto", "250", "2026-11-01")).toEqual({
      angebot_id: "a1",
      rechnungsart: "abschlag",
      abschlag_netto: "250",
      faellig_am: "2026-11-01",
    });
  });
});

describe("kannGutschriftErstellen", () => {
  const basis = { ist_storno: false, rechnungsart: "rechnung" as const };

  it("erlaubt Rechnung und Schlussrechnung ab Versand", () => {
    for (const status of ["versendet", "teilweise_bezahlt", "bezahlt"] as const) {
      expect(kannGutschriftErstellen({ ...basis, status })).toBe(true);
      expect(kannGutschriftErstellen({ ...basis, rechnungsart: "schluss", status })).toBe(true);
    }
  });

  it("verweigert Entwurf und storniert", () => {
    expect(kannGutschriftErstellen({ ...basis, status: "entwurf" })).toBe(false);
    expect(kannGutschriftErstellen({ ...basis, status: "storniert" })).toBe(false);
  });

  it("verweigert Abschlag, Gutschrift und Storno-Beleg", () => {
    expect(kannGutschriftErstellen({ ...basis, rechnungsart: "abschlag", status: "versendet" })).toBe(false);
    expect(kannGutschriftErstellen({ ...basis, rechnungsart: "gutschrift", status: "versendet" })).toBe(false);
    expect(kannGutschriftErstellen({ ...basis, ist_storno: true, status: "versendet" })).toBe(false);
  });

  it("behandelt fehlendes rechnungsart als normale Rechnung", () => {
    const r = { status: "versendet", ist_storno: false } as Pick<Rechnung, "status" | "ist_storno" | "rechnungsart">;
    expect(kannGutschriftErstellen(r)).toBe(true);
    expect(rechnungsartVon(r)).toBe("rechnung");
  });
});

describe("maxGutschriftMenge", () => {
  it("Menge minus bereits gutgeschrieben", () => {
    expect(maxGutschriftMenge(position({ menge: "10.00", bereits_gutgeschrieben: "2.50" }))).toBe(7.5);
    expect(maxGutschriftMenge(position({ menge: "3.00" }))).toBe(3);
  });

  it("Restmenge 0 oder überzogen ergibt 0", () => {
    expect(maxGutschriftMenge(position({ menge: "4.00", bereits_gutgeschrieben: "4.00" }))).toBe(0);
    expect(maxGutschriftMenge(position({ menge: "4.00", bereits_gutgeschrieben: "4.01" }))).toBe(0);
  });

  it("Abzugspositionen sind nie gutschreibbar", () => {
    expect(maxGutschriftMenge(position({ menge: "1.00", abschlag_rechnung_id: "ab1" }))).toBe(0);
  });
});

describe("restMenge", () => {
  it("zählt auch bei Abzugspositionen (für Komplett-Gutschrift)", () => {
    expect(restMenge(position({ menge: "1.00", abschlag_rechnung_id: "ab1" }))).toBe(1);
    expect(restMenge(position({ menge: "1.00", bereits_gutgeschrieben: "1.00" }))).toBe(0);
  });
});

describe("Gutschrift-Eingaben", () => {
  it("parseMenge versteht Komma und verwirft <= 0", () => {
    expect(parseMenge("1,5")).toBe(1.5);
    expect(parseMenge("0")).toBeNull();
    expect(parseMenge("-1")).toBeNull();
    expect(parseMenge("x")).toBeNull();
  });

  it("gutschriftMengeFehler prüft gegen die Restmenge", () => {
    const p = position({ menge: "10.00", bereits_gutgeschrieben: "8.00", einheit: "m" });
    expect(gutschriftMengeFehler(p, "2")).toBeNull();
    expect(gutschriftMengeFehler(p, "2,01")).toBe("Höchstens 2 m");
    expect(gutschriftMengeFehler(p, "")).toMatch(/größer als 0/);
  });

  it("Grund: 3 bis 200 Zeichen, getrimmt", () => {
    expect(gutschriftGrundFehler("  ab ")).toMatch(/Mindestens 3/);
    expect(gutschriftGrundFehler("abc")).toBeNull();
    expect(gutschriftGrundFehler("x".repeat(200))).toBeNull();
    expect(gutschriftGrundFehler("x".repeat(201))).toMatch(/Höchstens 200/);
  });

  it("gutschriftPayload: alle XOR positionen", () => {
    expect(gutschriftPayload("alle", { p1: "1" }, " Falsche Menge ")).toEqual({ alle: true, grund: "Falsche Menge" });
    expect(gutschriftPayload("positionen", { p1: "1,5" }, "Grund")).toEqual({
      positionen: [{ position_id: "p1", menge: "1.5" }],
      grund: "Grund",
    });
  });
});

describe("gutschriftSumme", () => {
  it("negativer Betrag, Steuer je Gruppe auf den Cent gerundet", () => {
    const s = gutschriftSumme(
      [
        { position: position({ id: "a", einzelpreis: "10.00", steuer_satz: "19.00", steuer_kategorie: "S" }), menge: "2" },
        { position: position({ id: "b", einzelpreis: "0.05", steuer_satz: "19.00", steuer_kategorie: "S" }), menge: "1" },
      ],
      "19",
    );
    // netto 20,05 -> Steuer 3,8095 -> 3,81
    expect(s).toEqual({ netto: "-20.05", steuer: "-3.81", brutto: "-23.86" });
  });

  it("mehrere Sätze getrennt, Position ohne Satz erbt den Belegsatz", () => {
    const s = gutschriftSumme(
      [
        { position: position({ id: "a", einzelpreis: "100.00", steuer_satz: "7.00", steuer_kategorie: "S" }), menge: "1" },
        { position: position({ id: "b", einzelpreis: "100.00" }), menge: "1" },
      ],
      "19",
    );
    expect(s).toEqual({ netto: "-200.00", steuer: "-26.00", brutto: "-226.00" });
  });

  it("leere Auswahl ergibt 0", () => {
    expect(gutschriftSumme([], "19")).toEqual({ netto: "0.00", steuer: "0.00", brutto: "0.00" });
  });
});

describe("Guthaben", () => {
  it("beschriftet negativen offenen Betrag als Guthaben", () => {
    expect(offenLabel("-119.00")).toBe("Guthaben");
    expect(offenLabel("0.00")).toBe("Offen");
    expect(offenAnzeige("-119.00")).toBe("119.00");
  });

  it("centZuText formatiert negative Beträge", () => {
    expect(centZuText(-5n)).toBe("-0.05");
    expect(centZuText(123456n)).toBe("1234.56");
  });
});
