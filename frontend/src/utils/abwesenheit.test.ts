import { describe, expect, it } from "vitest";

import type { Abwesenheit, AbwesenheitKalenderEintrag } from "../types";
import {
  ABWESENHEIT_ART_LABEL,
  abwesenheitStatusZuToken,
  formatTage,
  formatTageMitEinheit,
  formatZeitraum,
  kalenderRaster,
  kontoHinweis,
  offeneAntraege,
  resturlaubHinweis,
} from "./abwesenheit";
import { ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT, ZEITERFASSUNG_KATEGORIE_LABEL } from "./zeiterfassung";

function antrag(teil: Partial<Abwesenheit>): Abwesenheit {
  return {
    id: "a", user_id: "u", user_name: "Anna", art: "urlaub", von: "2026-03-02", bis: "2026-03-06",
    halber_tag_von: false, halber_tag_bis: false, tage: "4.0", status: "offen", notiz: null, antwort: null,
    erstellt_von: "u", erstellt_am: "2026-02-01T10:00:00Z", bearbeitet_von: null, bearbeitet_am: null,
    ...teil,
  };
}

describe("Labels und Toene", () => {
  it("kennt alle Arten", () => {
    expect(ABWESENHEIT_ART_LABEL.freizeitausgleich).toBe("Freizeitausgleich");
    expect(ZEITERFASSUNG_KATEGORIE_LABEL.freizeitausgleich).toBe("Freizeitausgleich");
    expect(ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT).toContain("freizeitausgleich");
  });
  it("bildet Status auf Status-Token ab", () => {
    expect(abwesenheitStatusZuToken("offen")).toBe("neu");
    expect(abwesenheitStatusZuToken("genehmigt")).toBe("erledigt");
    expect(abwesenheitStatusZuToken("abgelehnt")).toBe("fehlt");
    expect(abwesenheitStatusZuToken("zurueckgezogen")).toBe("geplant");
  });
});

describe("Formatierung", () => {
  it("Tage ohne unnoetige Nachkommastelle", () => {
    expect(formatTage("4.0")).toBe("4");
    expect(formatTage("4.5")).toBe("4,5");
    expect(formatTageMitEinheit("1.0")).toBe("1 Tag");
    expect(formatTageMitEinheit("0.5")).toBe("0,5 Tage");
  });
  it("Zeitraum", () => {
    expect(formatZeitraum(antrag({}))).toBe("02.03. – 06.03.2026");
    expect(formatZeitraum(antrag({ bis: "2026-03-02", halber_tag_von: true }))).toBe("02.03.2026 (halber Tag)");
    expect(formatZeitraum(antrag({ halber_tag_bis: true }))).toBe("02.03. – 06.03.2026 (letzter Tag halb)");
  });
});

describe("Urlaubskonto", () => {
  it("warnt nur bei negativem verbleibend", () => {
    expect(kontoHinweis({ verbleibend: "-2.5" })).toEqual({ ueberzogen: true, text: "Urlaubskonto um 2,5 Tage überzogen" });
    expect(kontoHinweis({ verbleibend: "0.0" }).ueberzogen).toBe(false);
    expect(kontoHinweis({ verbleibend: "12.0" }).text).toBeNull();
  });
  it("nennt Verfallsdatum des Resturlaubs", () => {
    const k = { resturlaub: "3.0", resturlaub_verfaellt_am: "2026-03-31", resturlaub_verfallen: "0.0" };
    expect(resturlaubHinweis(k)).toBe("Resturlaub verfällt am 31.03.2026");
    expect(resturlaubHinweis({ ...k, resturlaub_verfallen: "1.5" })).toBe("1,5 Tage Resturlaub am 31.03.2026 verfallen");
    expect(resturlaubHinweis({ ...k, resturlaub_verfaellt_am: null })).toBeNull();
    expect(resturlaubHinweis({ ...k, resturlaub: "0.0" })).toBeNull();
  });
});

describe("offeneAntraege", () => {
  it("filtert auf offen und sortiert nach Beginn", () => {
    const liste = [
      antrag({ id: "1", von: "2026-05-01" }),
      antrag({ id: "2", status: "genehmigt" }),
      antrag({ id: "3", von: "2026-04-01" }),
      antrag({ id: "4", status: "abgelehnt" }),
    ];
    expect(offeneAntraege(liste).map((a) => a.id)).toEqual(["3", "1"]);
  });
});

describe("kalenderRaster", () => {
  const e = (t: Partial<AbwesenheitKalenderEintrag>): AbwesenheitKalenderEintrag => ({
    id: "k", user_id: "u1", user_name: "Berta", art: "urlaub", von: "2026-03-02", bis: "2026-03-09",
    halber_tag_von: false, halber_tag_bis: false, tage: "6.0", ...t,
  });
  it("laesst Wochenenden leer und zaehlt halbe Tage", () => {
    const { tage, zeilen } = kalenderRaster([e({ halber_tag_bis: true })], 2026, 2);
    expect(tage).toHaveLength(31);
    const z = zeilen[0];
    expect(z.zellen.has("2026-03-07")).toBe(false); // Samstag
    expect(z.zellen.get("2026-03-09")).toEqual({ art: "urlaub", halb: true });
    expect(z.tage).toBe(5.5);
  });
  it("schneidet auf den Monat zu und sortiert nach Name", () => {
    const { zeilen } = kalenderRaster(
      [e({ user_id: "u2", user_name: "Zoe", von: "2026-02-26", bis: "2026-03-03" }), e({ user_name: "Anna", user_id: "u3" })],
      2026,
      2,
    );
    expect(zeilen.map((z) => z.user_name)).toEqual(["Anna", "Zoe"]);
    expect(zeilen[1].zellen.size).toBe(2); // 2.+3.3.
  });
  it("Krankheit hat Vorrang vor Urlaub am selben Tag", () => {
    const { zeilen } = kalenderRaster([e({}), e({ id: "k2", art: "krankheit", von: "2026-03-03", bis: "2026-03-03" })], 2026, 2);
    expect(zeilen[0].zellen.get("2026-03-03")?.art).toBe("krankheit");
    expect(zeilen[0].zellen.get("2026-03-04")?.art).toBe("urlaub");
  });
});
