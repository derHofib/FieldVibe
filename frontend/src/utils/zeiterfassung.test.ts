import { describe, expect, it } from "vitest";

import { toDateInput } from "./zeiterfassung";

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
