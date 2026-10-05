import { describe, expect, it } from "vitest";

import { arbeitsstunden, eintraegeJeTag, monatsGrenzen, tageDesMonats, toDateInput } from "./zeiterfassung";

describe("toDateInput", () => {
  it("gibt das lokale Kalenderdatum zurueck, nicht das UTC-Datum", () => {
    // Lokale Konstruktion (kein ISO-String) -- Date interpretiert die
    // Komponenten in der Zeitzone der laufenden Umgebung, genau wie
    // startOfWoche()/montagDerWoche() sie erzeugen. toDateInput() darf das
    // nicht ueber toISOString() (UTC) wieder verschieben (siehe Kommentar
    // an toDateInput -- sonst verschiebt sich z.B. ein Wochenfilter in
    // Europe/Berlin um einen Tag).
    const lokaleMitternacht = new Date(2026, 8, 28); // 28. September 2026, 00:00 lokal
    expect(toDateInput(lokaleMitternacht)).toBe("2026-09-28");
  });

  it("padded Monat und Tag einstellig auf zwei Stellen", () => {
    const lokaleMitternacht = new Date(2026, 0, 5); // 5. Januar 2026
    expect(toDateInput(lokaleMitternacht)).toBe("2026-01-05");
  });
});

describe("tageDesMonats", () => {
  it("liefert 28/29/30/31 Tage", () => {
    expect(tageDesMonats(2025, 1)).toHaveLength(28);
    expect(tageDesMonats(2024, 1)).toHaveLength(29);
    expect(tageDesMonats(2025, 3)).toHaveLength(30);
    expect(tageDesMonats(2025, 0)).toHaveLength(31);
  });

  it("setzt Wochentag ab Montag und markiert Wochenenden", () => {
    // 1.10.2026 ist ein Donnerstag
    const tage = tageDesMonats(2026, 9);
    expect(tage[0]).toMatchObject({ tag: "2026-10-01", tagNr: 1, wochentag: 3, istWochenende: false });
    expect(tage[2]).toMatchObject({ tag: "2026-10-03", wochentag: 5, istWochenende: true });
    expect(tage[3]).toMatchObject({ tag: "2026-10-04", wochentag: 6, istWochenende: true });
    expect(tage[4].wochentag).toBe(0);
    expect(tage[30].tag).toBe("2026-10-31");
  });
});

describe("monatsGrenzen", () => {
  it("nutzt Monatsersten und -letzten, auch im Schaltjahr und im Dezember", () => {
    expect(monatsGrenzen(2024, 1)).toEqual({ von: "2024-02-01", bis: "2024-02-29" });
    expect(monatsGrenzen(2025, 11)).toEqual({ von: "2025-12-01", bis: "2025-12-31" });
  });
});

describe("eintraegeJeTag / arbeitsstunden", () => {
  const lokal = (tag: string, uhr: string) => new Date(`${tag}T${uhr}`).toISOString();
  const e = (tag: string, von: string, bis: string | null, kategorie: "auftrag" | "pause" | "urlaub" = "auftrag") => ({
    start_at: lokal(tag, von),
    ende_at: bis ? lokal(tag, bis) : null,
    kategorie,
  });

  it("ordnet nach lokalem Tag zu (23:30 bleibt am selben Tag) und sortiert nach Start", () => {
    const map = eintraegeJeTag([
      e("2026-10-05", "23:30:00", "23:50:00"),
      e("2026-10-05", "08:00:00", "09:00:00"),
      e("2026-10-06", "08:00:00", "09:00:00"),
    ]);
    expect(map.get("2026-10-05")).toHaveLength(2);
    expect(map.get("2026-10-05")![0].start_at < map.get("2026-10-05")![1].start_at).toBe(true);
    expect(map.get("2026-10-06")).toHaveLength(1);
    expect(map.get("2026-10-07")).toBeUndefined();
  });

  it("summiert ohne Pause/Urlaub und zaehlt laufende Eintraege als 0", () => {
    const h = arbeitsstunden([
      e("2026-10-05", "08:00:00", "10:30:00"),
      e("2026-10-05", "10:30:00", "11:00:00", "pause"),
      e("2026-10-06", "00:00:00", "08:00:00", "urlaub"),
      e("2026-10-06", "12:00:00", null),
    ]);
    expect(h).toBeCloseTo(2.5, 5);
  });
});
