import { describe, expect, it } from "vitest";

import type { KennzahlGruppierung } from "../../types/kennzahlen";
import { effektiveGruppierung, verschieben, zeitGruppierungFuer, zeitraumBerechnen, zeitraumEnthaeltHeute } from "./zeitraum";

const tag = (iso: string) => new Date(`${iso}T12:00:00`);

describe("zeitraumBerechnen", () => {
  it("Woche: Montag bis Sonntag, Vorwoche, KW-Label", () => {
    const z = zeitraumBerechnen("woche", tag("2026-11-19"));
    expect(z).toMatchObject({
      von: "2026-11-16",
      bis: "2026-11-22",
      vergleich_von: "2026-11-09",
      vergleich_bis: "2026-11-15",
      label: "KW 47 2026",
      vorperiodeLabel: "Vorwoche",
    });
  });

  it("Woche über Silvester gehört zum Wochenjahr des Donnerstags", () => {
    const ende = zeitraumBerechnen("woche", tag("2027-01-01"));
    expect(ende).toMatchObject({ von: "2026-12-28", bis: "2027-01-03", label: "KW 53 2026" });
    const anfang = zeitraumBerechnen("woche", tag("2025-12-31"));
    expect(anfang).toMatchObject({ von: "2025-12-29", bis: "2026-01-04", label: "KW 1 2026" });
    expect(anfang.vergleich_von).toBe("2025-12-22");
  });

  it("Sonntag zählt noch zur laufenden Woche", () => {
    expect(zeitraumBerechnen("woche", tag("2026-11-22")).von).toBe("2026-11-16");
  });

  it("Monat: voller Monat, Vormonat mit Namen", () => {
    const z = zeitraumBerechnen("monat", tag("2026-11-19"));
    expect(z).toMatchObject({
      von: "2026-11-01",
      bis: "2026-11-30",
      vergleich_von: "2026-10-01",
      vergleich_bis: "2026-10-31",
      label: "November 2026",
      vorperiodeLabel: "Oktober",
    });
  });

  it("Monat im Januar vergleicht mit Dezember des Vorjahres (Schaltjahr-Februar inklusive)", () => {
    const jan = zeitraumBerechnen("monat", tag("2026-01-15"));
    expect(jan).toMatchObject({ vergleich_von: "2025-12-01", vergleich_bis: "2025-12-31", vorperiodeLabel: "Dezember" });
    expect(zeitraumBerechnen("monat", tag("2028-02-10")).bis).toBe("2028-02-29");
  });

  it("Quartal: Q4 mit Vorquartal Q3", () => {
    const z = zeitraumBerechnen("quartal", tag("2026-11-19"));
    expect(z).toMatchObject({
      von: "2026-10-01",
      bis: "2026-12-31",
      vergleich_von: "2026-07-01",
      vergleich_bis: "2026-09-30",
      label: "Q4 2026",
      vorperiodeLabel: "Q3 2026",
    });
  });

  it("Quartal: Q1 vergleicht mit Q4 des Vorjahres", () => {
    const z = zeitraumBerechnen("quartal", tag("2026-02-03"));
    expect(z).toMatchObject({
      von: "2026-01-01",
      bis: "2026-03-31",
      vergleich_von: "2025-10-01",
      vergleich_bis: "2025-12-31",
      vorperiodeLabel: "Q4 2025",
    });
  });

  it("Jahr: Vorjahr", () => {
    expect(zeitraumBerechnen("jahr", tag("2026-11-19"))).toMatchObject({
      von: "2026-01-01",
      bis: "2026-12-31",
      vergleich_von: "2025-01-01",
      vergleich_bis: "2025-12-31",
      label: "2026",
    });
  });

  it("Letzte 12 Monate: laufender Monat zählt mit, Vergleich sind die 12 Monate davor", () => {
    const z = zeitraumBerechnen("12_monate", tag("2026-11-19"));
    expect(z).toMatchObject({
      von: "2025-12-01",
      bis: "2026-11-30",
      vergleich_von: "2024-12-01",
      vergleich_bis: "2025-11-30",
      label: "Dez 2025 – Nov 2026",
    });
  });

  it("Letzte 12 Monate im Januar reichen ins Vorjahr", () => {
    const z = zeitraumBerechnen("12_monate", tag("2026-01-31"));
    expect(z).toMatchObject({ von: "2025-02-01", bis: "2026-01-31", vergleich_von: "2024-02-01", vergleich_bis: "2025-01-31" });
  });
});

describe("verschieben", () => {
  it("verschiebt Woche um sieben Tage", () => {
    expect(zeitraumBerechnen("woche", verschieben("woche", tag("2026-11-19"), -1)).label).toBe("KW 46 2026");
    expect(zeitraumBerechnen("woche", verschieben("woche", tag("2026-12-30"), 1)).label).toBe("KW 1 2027");
  });

  it("Monat: Jahreswechsel und kurzer Zielmonat ohne Überlauf", () => {
    expect(zeitraumBerechnen("monat", verschieben("monat", tag("2026-01-31"), -1)).label).toBe("Dezember 2025");
    expect(zeitraumBerechnen("monat", verschieben("monat", tag("2026-01-31"), 1)).label).toBe("Februar 2026");
  });

  it("Quartal, Jahr und 12 Monate", () => {
    expect(zeitraumBerechnen("quartal", verschieben("quartal", tag("2026-02-10"), -1)).label).toBe("Q4 2025");
    expect(zeitraumBerechnen("jahr", verschieben("jahr", tag("2026-06-10"), -1)).label).toBe("2025");
    expect(zeitraumBerechnen("12_monate", verschieben("12_monate", tag("2026-11-19"), -1)).label).toBe("Nov 2025 – Okt 2026");
  });
});

describe("zeitraumEnthaeltHeute", () => {
  it("ist wahr für den laufenden und falsch für vergangene Zeiträume", () => {
    const heute = tag("2026-11-19");
    expect(zeitraumEnthaeltHeute("monat", heute, heute)).toBe(true);
    expect(zeitraumEnthaeltHeute("monat", verschieben("monat", heute, -1), heute)).toBe(false);
    expect(zeitraumEnthaeltHeute("woche", tag("2026-11-22"), heute)).toBe(true);
  });
});

describe("zeitGruppierungFuer", () => {
  const woche: KennzahlGruppierung = { schluessel: "woche", label: "Woche", zeit: true };
  const monat: KennzahlGruppierung = { schluessel: "monat", label: "Monat", zeit: true };
  const techniker: KennzahlGruppierung = { schluessel: "techniker", label: "Techniker", zeit: false };

  it("Woche und Monat laufen wochenweise, Quartal bis 12 Monate monatsweise", () => {
    expect(zeitGruppierungFuer("woche", [woche, monat])).toBe("woche");
    expect(zeitGruppierungFuer("monat", [monat, woche])).toBe("woche");
    expect(zeitGruppierungFuer("quartal", [woche, monat])).toBe("monat");
    expect(zeitGruppierungFuer("12_monate", [woche, monat])).toBe("monat");
  });

  it("fällt auf die vorhandene Zeitachse zurück und liefert null ohne Zeit-Aufteilung", () => {
    expect(zeitGruppierungFuer("jahr", [woche])).toBe("woche");
    expect(zeitGruppierungFuer("monat", [techniker])).toBeNull();
  });
});

describe("effektiveGruppierung", () => {
  const woche: KennzahlGruppierung = { schluessel: "woche", label: "Woche", zeit: true };
  const monat: KennzahlGruppierung = { schluessel: "monat", label: "Monat", zeit: true };
  const techniker: KennzahlGruppierung = { schluessel: "techniker", label: "Techniker", zeit: false };
  const beide = [monat, woche, techniker];

  it("Woche/Monat/Quartal wochenweise, Jahr/12 Monate monatsweise", () => {
    for (const art of ["woche", "monat", "quartal"] as const) expect(effektiveGruppierung(art, beide, "monat")).toBe("woche");
    for (const art of ["jahr", "12_monate"] as const) expect(effektiveGruppierung(art, beide, "woche")).toBe("monat");
  });

  it("lässt Kategorien und nicht angebotene Achsen unverändert", () => {
    expect(effektiveGruppierung("monat", beide, "techniker")).toBe("techniker");
    expect(effektiveGruppierung("monat", [monat, techniker], "monat")).toBe("monat");
    expect(effektiveGruppierung("jahr", [woche], "woche")).toBe("woche");
  });
});
