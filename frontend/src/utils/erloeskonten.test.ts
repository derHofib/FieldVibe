import { describe, expect, it } from "vitest";

import {
  firmendatenMitKonten,
  kontenAusFirmendaten,
  kontenFehler,
  kontenZuPayload,
  leereKonten,
  validiereBu,
  validiereKonto,
} from "./erloeskonten";

describe("validiereKonto", () => {
  it("lässt leer sowie 4 bis 8 Ziffern zu", () => {
    expect(validiereKonto("")).toBeNull();
    expect(validiereKonto("8400")).toBeNull();
    expect(validiereKonto("12345678")).toBeNull();
  });

  it("lehnt 3 Ziffern, 9 Ziffern und Buchstaben ab", () => {
    expect(validiereKonto("840")).not.toBeNull();
    expect(validiereKonto("123456789")).not.toBeNull();
    expect(validiereKonto("84a0")).not.toBeNull();
  });
});

describe("validiereBu", () => {
  it("lässt leer sowie 1 bis 3 Ziffern mit Konto zu", () => {
    expect(validiereBu("", "")).toBeNull();
    expect(validiereBu("9", "8400")).toBeNull();
    expect(validiereBu("123", "8400")).toBeNull();
  });

  it("lehnt 4 Ziffern und Buchstaben ab", () => {
    expect(validiereBu("1234", "8400")).not.toBeNull();
    expect(validiereBu("a", "8400")).not.toBeNull();
  });

  it("lehnt einen BU-Schlüssel ohne Konto ab", () => {
    expect(validiereBu("9", "")).toMatch(/Konto/);
  });
});

describe("kontenFehler", () => {
  it("meldet je Zeile nur die fehlerhaften Felder", () => {
    const eingabe = leereKonten();
    eingabe["S:19.00"] = { konto: "840", bu: "" };
    eingabe["AE:0.00"] = { konto: "8337", bu: "1234" };
    expect(kontenFehler(eingabe)).toEqual({
      "S:19.00": { konto: "Konto: 4 bis 8 Ziffern" },
      "AE:0.00": { bu: "BU-Schlüssel: 1 bis 3 Ziffern" },
    });
  });

  it("ist leer, wenn alles gültig oder unbelegt ist", () => {
    expect(kontenFehler(leereKonten())).toEqual({});
  });
});

describe("kontenZuPayload", () => {
  it("sendet nur Zeilen mit Konto, getrimmt", () => {
    const eingabe = leereKonten();
    eingabe["Z:0.00"] = { konto: " 8337 ", bu: " 9 " };
    eingabe["E:0.00"] = { konto: "", bu: "7" };
    expect(kontenZuPayload(eingabe)).toEqual({ "Z:0.00": { konto: "8337", bu: "9" } });
  });
});

describe("kontenAusFirmendaten / firmendatenMitKonten", () => {
  it("liest gespeicherte Konten und füllt die übrigen Zeilen leer", () => {
    const eingabe = kontenAusFirmendaten({ buchhaltung: { erloeskonten: { "AE:0.00": { konto: "8337", bu: "" } } } });
    expect(eingabe["AE:0.00"]).toEqual({ konto: "8337", bu: "" });
    expect(eingabe["S:19.00"]).toEqual({ konto: "", bu: "" });
  });

  it("behält alle übrigen Firmendaten-Keys, auch unbekannte", () => {
    const fd = {
      ust_idnr: "DE1",
      impressum_url: "https://example.de/impressum",
      unbekannt: { x: 1 },
      buchhaltung: { erloeskonten: { "S:19.00": { konto: "8400", bu: "" } }, sonst: "bleibt" },
    } as Parameters<typeof firmendatenMitKonten>[0];
    const eingabe = leereKonten();
    eingabe["AE:0.00"] = { konto: "8337", bu: "" };
    const neu = firmendatenMitKonten(fd, eingabe) as Record<string, unknown>;
    expect(neu.ust_idnr).toBe("DE1");
    expect(neu.impressum_url).toBe("https://example.de/impressum");
    expect(neu.unbekannt).toEqual({ x: 1 });
    expect(neu.buchhaltung).toEqual({ erloeskonten: { "AE:0.00": { konto: "8337", bu: "" } }, sonst: "bleibt" });
  });
});
