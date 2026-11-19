import { describe, expect, it } from "vitest";

import type { KennzahlDef, KennzahlGruppierung } from "../../types/kennzahlen";
import { erlaubteDarstellungen, gruppierungenFuer, passendeGruppierung, richtungFuer, standardDarstellung } from "./darstellungen";
import { abweichung, formatAchse, formatWert } from "./format";
import { VORLAGEN, vorlageFuerKatalog } from "./vorlagen";

const MONAT: KennzahlGruppierung = { schluessel: "monat", label: "Monat", zeit: true };
const WOCHE: KennzahlGruppierung = { schluessel: "woche", label: "Woche", zeit: true };
const TECHNIKER: KennzahlGruppierung = { schluessel: "techniker", label: "Techniker", zeit: false };
const STATUS: KennzahlGruppierung = { schluessel: "status", label: "Status", zeit: false };

function def(teil: Partial<KennzahlDef>): KennzahlDef {
  return {
    schluessel: "vorgaenge.erstellt",
    titel: "Erstellte Vorgänge",
    beschreibung: "",
    bereich: "vorgaenge",
    einheit: "anzahl",
    art: "zeitraum",
    summierbar: true,
    gruppierungen: [MONAT, WOCHE, TECHNIKER, STATUS],
    ...teil,
  };
}

describe("erlaubteDarstellungen", () => {
  it("bietet bei Zeit- und Kategorie-Aufteilung alles an", () => {
    expect(erlaubteDarstellungen(def({}))).toEqual(["zahl", "zahl_verlauf", "saeulen", "linie", "balken", "ring", "tabelle"]);
  });

  it("Stand-Kennzahl ohne Zeit-Aufteilung: kein Verlauf, keine Linie", () => {
    const erlaubt = erlaubteDarstellungen(def({ art: "stand", gruppierungen: [STATUS, TECHNIKER] }));
    expect(erlaubt).not.toContain("linie");
    expect(erlaubt).not.toContain("zahl_verlauf");
    expect(erlaubt).toEqual(["zahl", "saeulen", "balken", "ring", "tabelle"]);
  });

  it("nicht summierbare Kennzahl (Durchlaufzeit) hat keinen Ring", () => {
    expect(erlaubteDarstellungen(def({ summierbar: false }))).not.toContain("ring");
  });

  it("Gesamt sperrt die Tabelle, jede andere Aufteilung erlaubt sie", () => {
    expect(erlaubteDarstellungen(def({}), "gesamt")).not.toContain("tabelle");
    expect(erlaubteDarstellungen(def({}), "techniker")).toContain("tabelle");
  });

  it("ohne Aufteilungen bleibt nur die Zahl", () => {
    expect(erlaubteDarstellungen(def({ gruppierungen: [] }))).toEqual(["zahl"]);
  });

  it("nur Zeit-Aufteilung: kein Balken, kein Ring", () => {
    const erlaubt = erlaubteDarstellungen(def({ gruppierungen: [MONAT] }));
    expect(erlaubt).toEqual(["zahl", "zahl_verlauf", "saeulen", "linie", "tabelle"]);
  });

  it("Standard ist die Zahl", () => {
    expect(standardDarstellung(def({}))).toBe("zahl");
  });
});

describe("passendeGruppierung / gruppierungenFuer", () => {
  it("Linie wählt Monat, wenn die bisherige Aufteilung keine Zeit ist", () => {
    expect(passendeGruppierung(def({}), "linie", "techniker")).toBe("monat");
    expect(passendeGruppierung(def({}), "linie", null)).toBe("monat");
  });

  it("behält eine passende Aufteilung bei", () => {
    expect(passendeGruppierung(def({}), "linie", "woche")).toBe("woche");
    expect(passendeGruppierung(def({}), "balken", "status")).toBe("status");
  });

  it("Balken/Ring/Tabelle fallen auf die erste Kategorie, Zahl auf keine", () => {
    expect(passendeGruppierung(def({}), "balken", "monat")).toBe("techniker");
    expect(passendeGruppierung(def({}), "ring", null)).toBe("techniker");
    expect(passendeGruppierung(def({}), "tabelle", null)).toBe("techniker");
    expect(passendeGruppierung(def({}), "zahl", "techniker")).toBeNull();
    expect(passendeGruppierung(def({}), "zahl_verlauf", "monat")).toBeNull();
  });

  it("filtert die Aufteilungen nach Darstellung", () => {
    expect(gruppierungenFuer(def({}), "linie").map((g) => g.schluessel)).toEqual(["monat", "woche"]);
    expect(gruppierungenFuer(def({}), "balken").map((g) => g.schluessel)).toEqual(["techniker", "status"]);
    expect(gruppierungenFuer(def({}), "zahl")).toEqual([]);
  });
});

describe("Richtung und Formatierung", () => {
  it("kennt Richtungen nur für Kennzahlen mit klarer Aussage", () => {
    expect(richtungFuer("vorgaenge.durchlaufzeit")).toBe("niedriger_besser");
    expect(richtungFuer("finanzen.umsatz_netto")).toBe("hoeher_besser");
    expect(richtungFuer("vorgaenge.erstellt")).toBe("neutral");
  });

  it("formatiert Werte deutsch", () => {
    const norm = (s: string) => s.replace(/ /g, " ");
    expect(norm(formatWert(1234.5, "eur"))).toBe("1.234,50 €");
    expect(norm(formatWert(48320.4, "eur"))).toBe("48.320 €");
    expect(formatWert(1234, "anzahl")).toBe("1.234");
    expect(norm(formatWert(4.2, "tage"))).toBe("4,2 Tage");
    expect(norm(formatWert(64, "prozent"))).toBe("64 %");
    expect(formatWert(320, "minuten")).toBe("5 h 20 min");
    expect(formatWert(45, "minuten")).toBe("45 min");
    expect(formatWert(null, "eur")).toBe("–");
  });

  it("kürzt Achsenwerte", () => {
    const norm = (s: string) => s.replace(/ /g, " ");
    expect(norm(formatAchse(12000, "eur"))).toBe("12 Tsd.");
    expect(norm(formatAchse(1_200_000, "eur"))).toBe("1,2 Mio.");
    expect(formatAchse(7, "anzahl")).toBe("7");
  });

  it("Abweichung: Pfeil als Text, Wertung nur bei klarer Richtung", () => {
    const norm = (s: string | undefined) => s?.replace(/ /g, " ");
    const umsatz = abweichung("finanzen.umsatz_netto", "eur", 112, 100, "Oktober");
    expect(norm(umsatz?.text)).toBe("▲ 12 % ggü. Oktober");
    expect(umsatz?.gut).toBe(true);
    const zeit = abweichung("vorgaenge.durchlaufzeit", "tage", 3.4, 4.2, "Oktober");
    expect(norm(zeit?.text)).toBe("▼ 0,8 Tage ggü. Oktober");
    expect(zeit?.gut).toBe(true);
    const erstellt = abweichung("vorgaenge.erstellt", "anzahl", 48, 42, "Oktober");
    expect(norm(erstellt?.text)).toBe("▲ 6 ggü. Oktober");
    expect(erstellt?.gut).toBeNull();
    expect(abweichung("vorgaenge.erstellt", "anzahl", 5, null, "Oktober")).toBeNull();
    expect(abweichung("vorgaenge.erstellt", "anzahl", 5, 5, "Oktober")?.richtung).toBe("gleich");
    // 0 gegen 0 sagt nichts aus.
    expect(abweichung("vorgaenge.erstellt", "anzahl", 0, 0, "Oktober")).toBeNull();
  });
});

describe("Vorlagen", () => {
  it("hat vier Vorlagen mit eindeutigen Widget-ids", () => {
    expect(VORLAGEN.map((v) => v.schluessel)).toEqual(["ueberblick", "vorgaenge", "finanzen", "team"]);
    const ids = VORLAGEN.flatMap((v) => v.layout.widgets.map((w) => w.id));
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("blendet Widgets ohne sichtbare Kennzahl aus und entfernt leere Vorlagen", () => {
    const katalog = new Set(["vorgaenge.offen", "vorgaenge.erstellt"]);
    const team = VORLAGEN.find((v) => v.schluessel === "team")!;
    const gekuerzt = vorlageFuerKatalog(team, katalog);
    expect(gekuerzt?.layout.widgets.map((w) => w.kennzahl)).toEqual(["vorgaenge.offen"]);
    // Das Original bleibt unangetastet.
    expect(team.layout.widgets).toHaveLength(4);
    const finanzen = VORLAGEN.find((v) => v.schluessel === "finanzen")!;
    expect(vorlageFuerKatalog(finanzen, katalog)).toBeNull();
  });
});
