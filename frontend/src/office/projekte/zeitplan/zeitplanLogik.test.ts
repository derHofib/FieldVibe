import { describe, expect, it } from "vitest";

import type { ZeitplanAbhaengigkeit, ZeitplanElement } from "../../../types";
import {
  addTage,
  anzeigeZeitraeume,
  berechneVorschau,
  dauerTage,
  diffTage,
  elementAenderung,
  formatBereich,
  formatTag,
  heuteTag,
  isoKw,
  istGueltigesVerbindungsziel,
  kopfSegmente,
  parseTag,
  phaseVerschieben,
  pixelZuTagen,
  PX_PRO_TAG,
  rundePfad,
  tagZuX,
  verbindungsPfad,
  verbindungsPunkte,
  wochentag,
  wuerdeKreisErzeugen,
  xZuTag,
  zeitbereich,
  type Aenderung,
  type Zoom,
} from "./zeitplanLogik";

function el(id: string, typ: ZeitplanElement["typ"], start: string | null, ende: string | null, phase: string | null = null): ZeitplanElement {
  return { id, typ, titel: id, phase_id: phase, start_am: start, ende_am: ende, fortschritt: 0, plan_reihenfolge: 0, zugewiesen_an: null, zugewiesen_name: null, erledigt: false };
}
function dep(v: string, n: string, versatz = 0): ZeitplanAbhaengigkeit {
  return { id: `${v}>${n}`, vorgaenger_id: v, nachfolger_id: n, art: "ende_anfang", versatz_tage: versatz };
}
const direkt = (id: string, s: string, e: string) => new Map<string, Aenderung>([[id, { start_am: s, ende_am: e }]]);

describe("Datumsmathe in Kalendertagen", () => {
  it("rechnet ueber Monatswechsel", () => {
    expect(addTage("2026-01-31", 1)).toBe("2026-02-01");
    expect(addTage("2026-03-01", -1)).toBe("2026-02-28");
    expect(addTage("2026-12-30", 3)).toBe("2027-01-02");
  });

  it("kennt Schaltjahre", () => {
    expect(addTage("2028-02-28", 1)).toBe("2028-02-29");
    expect(addTage("2028-02-28", 2)).toBe("2028-03-01");
    expect(addTage("2027-02-28", 1)).toBe("2027-03-01");
    expect(diffTage("2028-02-01", "2028-03-01")).toBe(29);
  });

  it("springt beim Sommerzeitwechsel nicht um einen Tag", () => {
    // Letzter Sonntag im Maerz (Umstellung auf Sommerzeit) und im Oktober.
    expect(addTage("2026-03-28", 1)).toBe("2026-03-29");
    expect(addTage("2026-03-29", 1)).toBe("2026-03-30");
    expect(addTage("2026-03-30", 1)).toBe("2026-03-31");
    expect(addTage("2026-10-24", 3)).toBe("2026-10-27");
    expect(addTage("2026-10-25", 1)).toBe("2026-10-26");
    expect(diffTage("2026-03-27", "2026-03-31")).toBe(4);
    expect(diffTage("2026-10-25", "2026-10-28")).toBe(3);
    for (let i = 0; i < 400; i++) expect(diffTage("2026-01-01", addTage("2026-01-01", i))).toBe(i);
  });

  it("parse/format sind zueinander invers", () => {
    for (const s of ["1999-12-31", "2000-02-29", "2026-10-25", "2026-03-29"]) expect(formatTag(parseTag(s))).toBe(s);
  });

  it("Wochentag und ISO-KW", () => {
    expect(wochentag(parseTag("2026-10-01"))).toBe(3); // Donnerstag
    expect(wochentag(parseTag("2026-10-05"))).toBe(0); // Montag
    expect(isoKw(parseTag("2026-01-01"))).toBe(1);
    expect(isoKw(parseTag("2026-12-31"))).toBe(53);
    expect(isoKw(parseTag("2027-01-01"))).toBe(53);
    expect(isoKw(parseTag("2027-01-04"))).toBe(1);
    expect(isoKw(parseTag("2026-10-12"))).toBe(42);
  });

  it("heuteTag nutzt die lokale Uhr", () => {
    expect(formatTag(heuteTag(new Date(2026, 9, 25, 23, 59)))).toBe("2026-10-25");
    expect(formatTag(heuteTag(new Date(2026, 2, 30, 0, 30)))).toBe("2026-03-30");
  });

  it("formatiert Bereiche inklusiv", () => {
    expect(dauerTage("2026-10-12", "2026-10-15")).toBe(4);
    expect(formatBereich("2026-10-12", "2026-10-15")).toBe("12.10. – 15.10. (4 Tage)");
    expect(formatBereich("2026-10-12", "2026-10-12")).toBe("12.10. – 12.10. (1 Tag)");
  });
});

describe("Pixel <-> Datum je Zoom", () => {
  const ursprung = parseTag("2026-10-05");
  for (const zoom of ["tag", "woche", "monat"] as Zoom[]) {
    it(`Rundreise im Zoom ${zoom}`, () => {
      const px = PX_PRO_TAG[zoom];
      for (const n of [0, 1, 9, 40]) {
        const x = tagZuX(ursprung + n, ursprung, zoom);
        expect(x).toBe(n * px);
        expect(xZuTag(x, ursprung, zoom)).toBe(ursprung + n);
        expect(xZuTag(x + px - 0.01, ursprung, zoom)).toBe(ursprung + n);
      }
    });
  }

  it("rastet Verschiebung aufs Tagesraster ein", () => {
    expect(pixelZuTagen(15, "tag")).toBe(0);
    expect(pixelZuTagen(17, "tag")).toBe(1);
    expect(pixelZuTagen(-50, "tag")).toBe(-2);
    expect(pixelZuTagen(30, "woche")).toBe(2);
    expect(pixelZuTagen(9, "monat")).toBe(2);
  });

  it("Kopf: Monate/KW/Tage", () => {
    const u = parseTag("2026-09-28"); // Montag
    const tag = kopfSegmente(u, 14, "tag");
    expect(tag.oben.map((s) => s.label)).toEqual(["September 2026", "Oktober 2026"]);
    expect(tag.oben[0].bis - tag.oben[0].von).toBe(3);
    expect(tag.unten).toHaveLength(14);
    const woche = kopfSegmente(u, 14, "woche");
    expect(woche.unten.map((s) => s.label)).toEqual(["KW 40", "KW 41"]);
    const monat = kopfSegmente(parseTag("2026-12-01"), 63, "monat");
    expect(monat.oben.map((s) => s.label)).toEqual(["2026", "2027"]);
    expect(monat.unten.map((s) => s.label)).toEqual(["Dez", "Jan", "Feb"]);
  });

  it("Zeitbereich umfasst alle Elemente und beginnt am Montag", () => {
    const heute = parseTag("2026-10-01");
    const b = zeitbereich([el("a", "schritt", "2026-09-20", "2026-12-24")], heute);
    expect(wochentag(b.ursprung)).toBe(0);
    expect(b.ursprung).toBeLessThanOrEqual(parseTag("2026-09-20"));
    expect(b.ursprung + b.anzahlTage).toBeGreaterThan(parseTag("2026-12-24"));
    expect(zeitbereich([], heute).anzahlTage).toBeGreaterThanOrEqual(63);
    expect(zeitbereich([], heute, 300).anzahlTage).toBeGreaterThanOrEqual(300);
  });
});

describe("Vorschau-Propagation", () => {
  // A (12.-14.) -> B (15.-17.), Dauer jeweils 3
  const a = el("A", "schritt", "2026-10-12", "2026-10-14");
  const b = el("B", "schritt", "2026-10-15", "2026-10-17");

  it("bei_konflikt: Nachfolger weicht nur nach hinten aus, Dauer bleibt", () => {
    const v = berechneVorschau([a, b], [dep("A", "B")], "bei_konflikt", direkt("A", "2026-10-14", "2026-10-16"));
    expect(v.get("B")).toEqual({ start_am: "2026-10-17", ende_am: "2026-10-19" });
  });

  it("bei_konflikt: Vorgaenger nach vorne laesst Nachfolger stehen", () => {
    const v = berechneVorschau([a, b], [dep("A", "B")], "bei_konflikt", direkt("A", "2026-10-10", "2026-10-12"));
    expect(v.has("B")).toBe(false);
  });

  it("bei_konflikt: Luecke wird aufgebraucht, bevor B wandert", () => {
    const b2 = el("B", "schritt", "2026-10-20", "2026-10-22");
    const v = berechneVorschau([a, b2], [dep("A", "B")], "bei_konflikt", direkt("A", "2026-10-14", "2026-10-16"));
    expect(v.has("B")).toBe(false);
  });

  it("immer: Nachfolger folgt auch nach vorne um dasselbe Delta", () => {
    const vor = berechneVorschau([a, b], [dep("A", "B")], "immer", direkt("A", "2026-10-10", "2026-10-12"));
    expect(vor.get("B")).toEqual({ start_am: "2026-10-13", ende_am: "2026-10-15" });
    const zurueck = berechneVorschau([a, b], [dep("A", "B")], "immer", direkt("A", "2026-10-14", "2026-10-16"));
    expect(zurueck.get("B")).toEqual({ start_am: "2026-10-17", ende_am: "2026-10-19" });
  });

  it("Versatz: +2 Wartezeit, -1 Ueberlappung", () => {
    const b2 = el("B", "schritt", "2026-10-17", "2026-10-18");
    const v = berechneVorschau([a, b2], [dep("A", "B", 2)], "bei_konflikt", direkt("A", "2026-10-12", "2026-10-15"));
    // frueheste Start = 15. + 1 + 2 = 18.
    expect(v.get("B")).toEqual({ start_am: "2026-10-18", ende_am: "2026-10-19" });
    const b3 = el("B", "schritt", "2026-10-14", "2026-10-15");
    const v2 = berechneVorschau([a, b3], [dep("A", "B", -1)], "bei_konflikt", direkt("A", "2026-10-12", "2026-10-15"));
    // frueheste Start = 15. + 1 - 1 = 15.
    expect(v2.get("B")).toEqual({ start_am: "2026-10-15", ende_am: "2026-10-16" });
  });

  it("Kette wandert komplett mit", () => {
    const c = el("C", "schritt", "2026-10-18", "2026-10-19");
    const v = berechneVorschau([a, b, c], [dep("A", "B"), dep("B", "C")], "bei_konflikt", direkt("A", "2026-10-13", "2026-10-15"));
    expect(v.get("B")).toEqual({ start_am: "2026-10-16", ende_am: "2026-10-18" });
    expect(v.get("C")).toEqual({ start_am: "2026-10-19", ende_am: "2026-10-20" });
  });

  it("Diamant: D haengt an B und C und nimmt das Maximum", () => {
    const x = el("A", "schritt", "2026-10-12", "2026-10-12");
    const bb = el("B", "schritt", "2026-10-13", "2026-10-14");
    const c = el("C", "schritt", "2026-10-13", "2026-10-18");
    const d = el("D", "schritt", "2026-10-19", "2026-10-20");
    const deps = [dep("A", "B"), dep("A", "C"), dep("B", "D"), dep("C", "D")];
    // A um 1 Tag nach hinten: B 14.-15., C 14.-19., D muss hinter C (ende 19.) -> 20.
    const v = berechneVorschau([x, bb, c, d], deps, "bei_konflikt", direkt("A", "2026-10-13", "2026-10-13"));
    expect(v.get("C")).toEqual({ start_am: "2026-10-14", ende_am: "2026-10-19" });
    expect(v.get("D")).toEqual({ start_am: "2026-10-20", ende_am: "2026-10-21" });
    // Reihenfolge der Abhaengigkeiten darf nichts aendern.
    const v2 = berechneVorschau([d, c, bb, x], [...deps].reverse(), "bei_konflikt", direkt("A", "2026-10-13", "2026-10-13"));
    expect(v2.get("D")).toEqual(v.get("D"));
  });

  it("Diamant im Modus immer: groesstes Delta, danach Konfliktregel", () => {
    const x = el("A", "schritt", "2026-10-12", "2026-10-12");
    const bb = el("B", "schritt", "2026-10-13", "2026-10-14");
    const c = el("C", "schritt", "2026-10-13", "2026-10-18");
    const d = el("D", "schritt", "2026-10-19", "2026-10-20");
    const deps = [dep("A", "B"), dep("A", "C"), dep("B", "D"), dep("C", "D")];
    // A zwei Tage nach vorne: B und C wandern -2; D wandert -2 -> 17., aber C endet 16. -> frueh. 17. ok.
    const v = berechneVorschau([x, bb, c, d], deps, "immer", direkt("A", "2026-10-10", "2026-10-10"));
    expect(v.get("B")).toEqual({ start_am: "2026-10-11", ende_am: "2026-10-12" });
    expect(v.get("C")).toEqual({ start_am: "2026-10-11", ende_am: "2026-10-16" });
    expect(v.get("D")).toEqual({ start_am: "2026-10-17", ende_am: "2026-10-18" });
  });

  it("Meilenstein als Vorgaenger: Datum + Versatz (kein +1)", () => {
    const m = el("M", "meilenstein", "2026-10-14", "2026-10-14");
    const s = el("S", "schritt", "2026-10-14", "2026-10-15");
    const v = berechneVorschau([m, s], [dep("M", "S")], "bei_konflikt", direkt("M", "2026-10-16", "2026-10-16"));
    expect(v.get("S")).toEqual({ start_am: "2026-10-16", ende_am: "2026-10-17" });
    const v2 = berechneVorschau([m, s], [dep("M", "S", 2)], "bei_konflikt", direkt("M", "2026-10-16", "2026-10-16"));
    expect(v2.get("S")).toEqual({ start_am: "2026-10-18", ende_am: "2026-10-19" });
  });

  it("Meilenstein als Nachfolger bleibt ein Tag", () => {
    const m = el("M", "meilenstein", "2026-10-15", "2026-10-15");
    const v = berechneVorschau([a, m], [dep("A", "M")], "bei_konflikt", direkt("A", "2026-10-12", "2026-10-17"));
    expect(v.get("M")).toEqual({ start_am: "2026-10-18", ende_am: "2026-10-18" });
  });

  it("Dauer aendern schiebt Nachfolger", () => {
    const aenderung = elementAenderung(a, "dauer", 2)!;
    expect(aenderung).toEqual({ start_am: "2026-10-12", ende_am: "2026-10-16" });
    const v = berechneVorschau([a, b], [dep("A", "B")], "bei_konflikt", direkt("A", aenderung.start_am, aenderung.ende_am));
    expect(v.get("B")?.start_am).toBe("2026-10-17");
  });

  it("Dauer ist mindestens 1 Tag, Meilenstein hat keine Dauer", () => {
    expect(elementAenderung(a, "dauer", -10)).toEqual({ start_am: "2026-10-12", ende_am: "2026-10-12" });
    expect(elementAenderung(el("M", "meilenstein", "2026-10-12", null), "dauer", 3)).toBeNull();
  });

  it("Phase verschieben: alle Kinder um Delta, Nachfolger ausserhalb ziehen mit", () => {
    const p = el("P", "phase", null, null);
    const k1 = el("K1", "schritt", "2026-10-12", "2026-10-14", "P");
    const k2 = el("K2", "schritt", "2026-10-15", "2026-10-16", "P");
    const ausser = el("X", "schritt", "2026-10-17", "2026-10-18");
    const aend = phaseVerschieben([p, k1, k2, ausser], "P", 3);
    expect(aend.get("K1")).toEqual({ start_am: "2026-10-15", ende_am: "2026-10-17" });
    expect(aend.get("K2")).toEqual({ start_am: "2026-10-18", ende_am: "2026-10-19" });
    expect(aend.has("X")).toBe(false);
    const v = berechneVorschau([p, k1, k2, ausser], [dep("K1", "K2"), dep("K2", "X")], "bei_konflikt", aend);
    expect(v.get("K1")).toEqual(aend.get("K1"));
    expect(v.get("X")).toEqual({ start_am: "2026-10-20", ende_am: "2026-10-21" });
  });

  it("Phasen-Spanne = min/max der Kinder, folgt der Vorschau", () => {
    const p = el("P", "phase", null, null);
    const k1 = el("K1", "schritt", "2026-10-12", "2026-10-14", "P");
    const k2 = el("K2", "schritt", "2026-10-15", "2026-10-16", "P");
    const z = anzeigeZeitraeume([p, k1, k2]);
    expect(z.get("P")).toEqual({ start: parseTag("2026-10-12"), ende: parseTag("2026-10-16") });
    const z2 = anzeigeZeitraeume([p, k1, k2], new Map([["K2", { start_am: "2026-10-20", ende_am: "2026-10-22" }]]));
    expect(z2.get("P")).toEqual({ start: parseTag("2026-10-12"), ende: parseTag("2026-10-22") });
  });

  it("ignoriert Elemente ohne Datum", () => {
    const ohne = el("O", "schritt", null, null);
    const v = berechneVorschau([a, ohne], [dep("A", "O")], "bei_konflikt", direkt("A", "2026-10-20", "2026-10-22"));
    expect(v.has("O")).toBe(false);
  });
});

describe("Zyklus-Erkennung", () => {
  const deps = [dep("A", "B"), dep("B", "C")];
  it("erkennt Selbstverbindung, direkten und indirekten Kreis", () => {
    expect(wuerdeKreisErzeugen(deps, "A", "A")).toBe(true);
    expect(wuerdeKreisErzeugen(deps, "B", "A")).toBe(true);
    expect(wuerdeKreisErzeugen(deps, "C", "A")).toBe(true);
  });
  it("erlaubt azyklische Verbindungen (auch Diamant)", () => {
    expect(wuerdeKreisErzeugen(deps, "A", "C")).toBe(false);
    expect(wuerdeKreisErzeugen(deps, "C", "D")).toBe(false);
    expect(wuerdeKreisErzeugen([dep("A", "B"), dep("A", "C"), dep("B", "D")], "C", "D")).toBe(false);
  });
  it("gueltige Ziele: keine Phase, kein Duplikat, nur mit Datum", () => {
    const e = [el("A", "schritt", "2026-10-12", "2026-10-13"), el("B", "meilenstein", "2026-10-14", null), el("P", "phase", null, null), el("O", "schritt", null, null)];
    expect(istGueltigesVerbindungsziel(e, [], "A", "B")).toBe(true);
    expect(istGueltigesVerbindungsziel(e, [], "A", "P")).toBe(false);
    expect(istGueltigesVerbindungsziel(e, [], "P", "A")).toBe(false);
    expect(istGueltigesVerbindungsziel(e, [], "A", "A")).toBe(false);
    expect(istGueltigesVerbindungsziel(e, [], "A", "O")).toBe(false);
    expect(istGueltigesVerbindungsziel(e, [dep("A", "B")], "A", "B")).toBe(false);
    expect(istGueltigesVerbindungsziel(e, [dep("A", "B")], "B", "A")).toBe(false);
  });
});

describe("Verbindungslinien", () => {
  it("Normalfall: rechts, senkrecht, rechts", () => {
    const p = verbindungsPunkte({ x: 100, y: 18 }, { x: 160, y: 54 });
    expect(p).toEqual([
      { x: 100, y: 18 },
      { x: 108, y: 18 },
      { x: 108, y: 54 },
      { x: 160, y: 54 },
    ]);
  });

  it("Umweg nach unten, wenn der Nachfolger links vom Vorgaenger-Ende liegt", () => {
    const p = verbindungsPunkte({ x: 100, y: 18 }, { x: 60, y: 54 });
    expect(p).toHaveLength(6);
    expect(p[2].y).toBe(36); // Zeilengrenze unter dem Vorgaenger
    expect(p[3].x).toBe(52); // links vor dem Nachfolger
    expect(p[5]).toEqual({ x: 60, y: 54 });
    expect(p[4].x).toBe(52);
  });

  it("Umweg auch bei direkt anschliessendem Nachfolger (kein Platz fuer Pfeil)", () => {
    expect(verbindungsPunkte({ x: 100, y: 18 }, { x: 100, y: 54 })).toHaveLength(6);
  });

  it("Nachfolger oberhalb: Umweg nach oben", () => {
    const p = verbindungsPunkte({ x: 100, y: 90 }, { x: 60, y: 54 });
    expect(p[2].y).toBe(72);
  });

  it("Pfad beginnt/endet an den Punkten und rundet Ecken", () => {
    const d = verbindungsPfad({ x: 100, y: 18 }, { x: 160, y: 54 });
    expect(d.startsWith("M 100 18")).toBe(true);
    expect(d.endsWith("L 160 54")).toBe(true);
    expect(d.match(/Q/g)).toHaveLength(2);
    expect(d).not.toMatch(/NaN/);
  });

  it("Rundung wird bei kurzen Segmenten begrenzt, doppelte Punkte entfallen", () => {
    const d = rundePfad([{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 4 }], 5);
    expect(d).toBe("M 0 0 L 2 0 Q 4 0 4 2 L 4 4");
  });
});
