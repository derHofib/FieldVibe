import { describe, expect, it } from "vitest";

import type { ZeitplanAntrag } from "../../../types";
import {
  antragFehler,
  antragVorbelegung,
  antragZeitText,
  baueAntrag,
  beantragbareArten,
  endeNachVerschieben,
  offeneAntraegeGesamt,
} from "./antragLogik";

const schritt = { id: "s1", typ: "schritt" as const, start_am: "2026-10-12", ende_am: "2026-10-14" };

describe("beantragbareArten", () => {
  it("Phasen nie, Lieferungen nur Problem, Meilensteine ohne Dauer", () => {
    expect(beantragbareArten({ typ: "phase", datum_gesperrt: false })).toEqual([]);
    expect(beantragbareArten({ typ: "meilenstein", datum_gesperrt: true })).toEqual(["problem"]);
    expect(beantragbareArten({ typ: "meilenstein", datum_gesperrt: false })).toEqual(["verschieben", "problem"]);
    expect(beantragbareArten({ typ: "schritt", datum_gesperrt: false })).toEqual(["verschieben", "dauer_aendern", "problem"]);
  });
});

describe("Vorbelegung und Ende", () => {
  it("übernimmt den Plan bzw. fällt auf heute zurück", () => {
    expect(antragVorbelegung(schritt)).toEqual({ start: "2026-10-12", ende: "2026-10-14" });
    expect(antragVorbelegung({ start_am: null, ende_am: null }, Date.UTC(2026, 9, 1) / 86_400_000)).toEqual({
      start: "2026-10-01",
      ende: "2026-10-01",
    });
  });
  it("behält beim Verschieben die Dauer", () => {
    expect(endeNachVerschieben(schritt, "2026-10-20")).toBe("2026-10-22");
    expect(endeNachVerschieben({ start_am: null, ende_am: null }, "2026-10-20")).toBe("2026-10-20");
  });
});

describe("antragFehler / baueAntrag", () => {
  it("verlangt eine Begründung und plausible Daten", () => {
    const d = { start: "2026-10-20", ende: "2026-10-22" };
    expect(antragFehler(schritt, "problem", d, "  ")).toMatch(/Begründung/);
    expect(antragFehler(schritt, "problem", d, "Material fehlt")).toBeNull();
    expect(antragFehler(schritt, "dauer_aendern", { start: "", ende: "2026-10-10" }, "x")).toMatch(/vor dem Start/);
    expect(antragFehler(schritt, "verschieben", { start: "", ende: "" }, "x")).toMatch(/Start/);
  });
  it("sendet je Art nur die passenden Felder", () => {
    const d = { start: "2026-10-20", ende: "2026-10-25" };
    expect(baueAntrag(schritt, "verschieben", d, " Regen ")).toEqual({
      element_id: "s1",
      art: "verschieben",
      begruendung: "Regen",
      gewuenschter_start_am: "2026-10-20",
      gewuenschtes_ende_am: "2026-10-22",
    });
    expect(baueAntrag(schritt, "dauer_aendern", d, "x")).toEqual({
      element_id: "s1",
      art: "dauer_aendern",
      begruendung: "x",
      gewuenschtes_ende_am: "2026-10-25",
    });
    expect(baueAntrag(schritt, "problem", d, "x")).toEqual({ element_id: "s1", art: "problem", begruendung: "x" });
    const ms = baueAntrag({ ...schritt, typ: "meilenstein" }, "verschieben", d, "x");
    expect(ms.gewuenschtes_ende_am).toBe("2026-10-20");
  });
});

describe("Anzeige", () => {
  const basis: ZeitplanAntrag = {
    id: "a", element_id: "s1", element_titel: "Rohbau", art: "verschieben",
    gewuenschter_start_am: "2026-10-19", gewuenschtes_ende_am: "2026-10-21",
    aktueller_start_am: "2026-10-12", aktuelles_ende_am: "2026-10-14",
    begruendung: "x", status: "offen", antwort: null, erstellt_von: "u", erstellt_von_name: "Tom",
    erstellt_am: "2026-10-01T10:00:00Z", bearbeitet_von_name: null, bearbeitet_am: null,
  };
  it("zeigt aktuell → gewünscht", () => {
    expect(antragZeitText(basis)).toBe("12.10. – 14.10. → 19.10. – 21.10.");
    expect(antragZeitText({ ...basis, art: "problem" })).toBe("Problem gemeldet");
  });
  it("summiert offene Anträge", () => {
    expect(offeneAntraegeGesamt([{ offene_antraege: 2 }, { offene_antraege: 0 }, { offene_antraege: 1 }])).toBe(3);
  });
});
