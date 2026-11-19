import { describe, expect, it } from "vitest";

import { UHR_MAX_ALTER_MS, UHR_SCHLUESSEL, formatUhr, uhrLaden, uhrLoeschen, uhrSekunden, uhrStarten, uhrStoppen, type UhrSpeicher } from "./anrufUhr";

function speicher(): UhrSpeicher & { daten: Map<string, string> } {
  const daten = new Map<string, string>();
  return {
    daten,
    getItem: (k) => daten.get(k) ?? null,
    setItem: (k, v) => void daten.set(k, v),
    removeItem: (k) => void daten.delete(k),
  };
}

describe("Anruf-Uhr", () => {
  it("startet, zählt Sekunden und formatiert mm:ss", () => {
    const sp = speicher();
    const uhr = uhrStarten({ kundeId: "k1", partnerName: "Reichel" }, 1_000_000, sp);
    expect(uhrSekunden(uhr, 1_000_000 + 125_900)).toBe(125);
    expect(formatUhr(125)).toBe("02:05");
    expect(formatUhr(4503)).toBe("75:03");
  });

  it("stellt die Uhr nach einem Neuladen aus dem Speicher wieder her", () => {
    const sp = speicher();
    uhrStarten({ kundeId: "k1", vorgangId: "v1", ansprechpartnerId: "a1", partnerName: "Reichel", partnerNummer: "030 1" }, 5_000, sp);
    const geladen = uhrLaden(5_000 + 90_000, sp);
    expect(geladen).toMatchObject({ start: 5_000, kundeId: "k1", vorgangId: "v1", ansprechpartnerId: "a1", partnerName: "Reichel" });
  });

  it("Stopp liefert Sekunden und Beginn und räumt den Speicher auf", () => {
    const sp = speicher();
    const uhr = uhrStarten({}, 10_000, sp);
    const ergebnis = uhrStoppen(uhr, 10_000 + 367_000, sp);
    expect(ergebnis.dauerSekunden).toBe(367);
    expect(ergebnis.beginn.getTime()).toBe(10_000);
    expect(sp.daten.has(UHR_SCHLUESSEL)).toBe(false);
  });

  it("verwirft zu alte, kaputte oder in der Zukunft liegende Einträge", () => {
    const sp = speicher();
    uhrStarten({}, 0, sp);
    expect(uhrLaden(UHR_MAX_ALTER_MS + 1, sp)).toBeNull();
    expect(sp.daten.has(UHR_SCHLUESSEL)).toBe(false);
    sp.setItem(UHR_SCHLUESSEL, "{kaputt");
    expect(uhrLaden(1, sp)).toBeNull();
    sp.setItem(UHR_SCHLUESSEL, JSON.stringify({ start: 10_000_000 }));
    expect(uhrLaden(1_000, sp)).toBeNull();
  });

  it("läuft auch ohne Speicher oder bei werfendem Speicher weiter", () => {
    const werfend: UhrSpeicher = {
      getItem: () => {
        throw new Error("gesperrt");
      },
      setItem: () => {
        throw new Error("gesperrt");
      },
      removeItem: () => {
        throw new Error("gesperrt");
      },
    };
    const uhr = uhrStarten({}, 1000, werfend);
    expect(uhr.start).toBe(1000);
    expect(uhrLaden(2000, werfend)).toBeNull();
    expect(() => uhrLoeschen(werfend)).not.toThrow();
    expect(uhrStarten({}, 1000, null).start).toBe(1000);
  });

  it("zählt nie negativ, wenn die Geräteuhr zurückspringt", () => {
    expect(uhrSekunden({ start: 10_000 }, 5_000)).toBe(0);
  });
});
