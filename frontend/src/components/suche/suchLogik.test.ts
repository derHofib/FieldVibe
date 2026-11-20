import { describe, expect, it } from "vitest";

import type { SearchHit } from "../../types";
import {
  formatAnzahl,
  kategorienLeiste,
  kategorieErreichbar,
  listenPfad,
  statusAnzeige,
  trefferZuEintrag,
  zielPfad,
} from "./kategorien";
import { gruppiereTreffer, zeitraumZuSeit } from "./useGlobaleSuche";

function hit(kategorie: SearchHit["kategorie"], id: string, titel: string, extra: Partial<SearchHit> = {}): SearchHit {
  return { kategorie, id, titel, subtitel: null, ...extra };
}

describe("gruppiereTreffer", () => {
  const treffer = [
    hit("kunde", "k1", "Müller GmbH"),
    hit("vorgang", "v1", "V-2026-0142: Heizung", { nummer: "V-2026-0142" }),
    hit("rechnung", "r1", "R-2026-0091", { nummer: "R-2026-0091" }),
    hit("anlage", "a1", "Therme"),
  ];

  it("ohne exakten Treffer gilt die feste Reihenfolge", () => {
    expect(gruppiereTreffer(treffer, "gmbh").map((g) => g.kategorie)).toEqual(["vorgang", "kunde", "anlage", "rechnung"]);
  });

  it("exakter Nummerntreffer setzt seine Gruppe an die Spitze", () => {
    expect(gruppiereTreffer(treffer, "r-2026-0091").map((g) => g.kategorie)).toEqual([
      "rechnung",
      "vorgang",
      "kunde",
      "anlage",
    ]);
  });

  it("Titelpräfix zählt, case-insensitiv", () => {
    expect(gruppiereTreffer(treffer, "MÜLLER")[0].kategorie).toBe("kunde");
  });

  it("lässt leere Gruppen weg", () => {
    expect(gruppiereTreffer([hit("tag", "t1", "#ems")], "ems").map((g) => g.kategorie)).toEqual(["tag"]);
  });
});

describe("kategorienLeiste", () => {
  const anzahl = { vorgang: 8, kunde: 3, anlage: 4, rechnung: 5, angebot: 2, telefonat: 1, projekt: 0 };
  const erlaubt = ["vorgang", "kunde", "anlage", "rechnung", "angebot", "auftrag", "projekt", "telefonat", "tag"] as const;

  it("zeigt die vier stärksten Kategorien, der Rest wandert in Mehr", () => {
    const l = kategorienLeiste({ anzahl, erlaubt: [...erlaubt], gewaehlt: "alle" });
    expect(l.sichtbar).toEqual(["vorgang", "rechnung", "anlage", "kunde"]);
    expect(l.mehr).toEqual(["angebot", "telefonat"]);
  });

  it("blendet Kategorien ohne Treffer aus", () => {
    const l = kategorienLeiste({ anzahl, erlaubt: [...erlaubt], gewaehlt: "alle" });
    expect([...l.sichtbar, ...l.mehr]).not.toContain("projekt");
  });

  it("zeigt Kategorien nicht, die in anzahl fehlen (Rechte)", () => {
    const l = kategorienLeiste({ anzahl: { vorgang: 2, kunde: 1 }, erlaubt: [...erlaubt], gewaehlt: "alle" });
    expect([...l.sichtbar, ...l.mehr]).toEqual(["vorgang", "kunde"]);
  });

  it("hält die gewählte Kategorie sichtbar, auch wenn sie nicht unter den vier stärksten ist", () => {
    const l = kategorienLeiste({ anzahl, erlaubt: [...erlaubt], gewaehlt: "telefonat" });
    expect(l.sichtbar).toContain("telefonat");
    expect(l.sichtbar).toHaveLength(4);
  });

  it("ohne Suchbegriff: feste Reihenfolge Vorgänge, Kunden, Anlagen, Rechnungen, Rest in Mehr", () => {
    const l = kategorienLeiste({ anzahl: undefined, erlaubt: [...erlaubt], gewaehlt: "alle" });
    expect(l.sichtbar).toEqual(["vorgang", "kunde", "anlage", "rechnung"]);
    expect(l.mehr).toEqual(["angebot", "auftrag", "projekt", "telefonat"]);
  });
});

describe("zeitraumZuSeit", () => {
  const jetzt = new Date(2026, 10, 19, 12, 0, 0); // 19.11.2026 lokal

  it("übersetzt die festen Zeiträume", () => {
    expect(zeitraumZuSeit("beliebig", jetzt)).toBeUndefined();
    expect(zeitraumZuSeit("heute", jetzt)).toBe("2026-11-19");
    expect(zeitraumZuSeit("7", jetzt)).toBe("2026-11-12");
    expect(zeitraumZuSeit("30", jetzt)).toBe("2026-10-20");
    expect(zeitraumZuSeit("jahr", jetzt)).toBe("2026-01-01");
  });

  it("nimmt das Datum des eigenen Zeitraums, leer = kein Filter", () => {
    expect(zeitraumZuSeit({ von: "2026-05-01" }, jetzt)).toBe("2026-05-01");
    expect(zeitraumZuSeit({ von: "" }, jetzt)).toBeUndefined();
  });
});

describe("Ziele und Anzeige", () => {
  it("Ziele je Kategorie (Office)", () => {
    expect(zielPfad("vorgang", "1", "x", "office")).toBe("/vorgaenge/1");
    expect(zielPfad("kunde", "1", "x", "office")).toBe("/kunden/1");
    expect(zielPfad("anlage", "1", "x", "office")).toBe("/anlagen/1");
    expect(zielPfad("rechnung", "1", "x", "office")).toBe("/rechnungen/1");
    expect(zielPfad("angebot", "1", "x", "office")).toBe("/angebote/1");
    expect(zielPfad("auftrag", "1", "x", "office")).toBe("/auftraege?auftrag=1");
    expect(zielPfad("projekt", "1", "x", "office")).toBe("/projekte?projekt=1");
    expect(zielPfad("telefonat", "1", "Frau Weber", "office")).toBe("/telefonate?q=Frau%20Weber");
    expect(zielPfad("tag", "1", "ems", "office")).toBeNull();
  });

  it("Feld-App verlinkt nur, was es dort gibt", () => {
    expect(kategorieErreichbar("auftrag", "feld")).toBe(false);
    expect(zielPfad("projekt", "1", "x", "feld")).toBeNull();
    expect(zielPfad("rechnung", "1", "x", "feld")).toBe("/rechnungen/1");
  });

  it("Listenpfad übernimmt q und bei Nur offene den Status-Filter der Vorgangsliste", () => {
    expect(listenPfad("kunde", "müller", false)).toBe("/kunden?q=m%C3%BCller");
    const vorgang = listenPfad("vorgang", "müller", true) ?? "";
    expect(vorgang).toContain("/vorgaenge?q=");
    expect(decodeURIComponent(vorgang)).toContain('["status","ist_nicht",["abgeschlossen","abgerechnet","storniert"]]');
    expect(listenPfad("kunde", "x", true)).not.toContain("f=");
    expect(listenPfad("anlage", "x", false)).toBeNull();
  });

  it("Status-Pillen nutzen die bestehenden Labels und Tokens", () => {
    expect(statusAnzeige("vorgang", "in_arbeit")).toEqual({ token: "arbeit", label: "In Arbeit" });
    expect(statusAnzeige("rechnung", "bezahlt")).toEqual({ token: "erledigt", label: "Bezahlt" });
    expect(statusAnzeige("angebot", "abgelehnt")).toEqual({ token: "fehlt", label: "Abgelehnt" });
    expect(statusAnzeige("auftrag", "offen")?.label).toBe("Offen");
    expect(statusAnzeige("kunde", null)).toBeNull();
  });

  it("Treffer: Vorgangstitel mit ' · ', Untertitel aus strukturierten Feldern", () => {
    const e = trefferZuEintrag(
      hit("vorgang", "v1", "V-2026-0142: Heizung", {
        nummer: "V-2026-0142",
        kunde_name: "Müller GmbH",
        datum: "2026-11-20",
        status: "in_arbeit",
      }),
      "office",
    );
    expect(e?.titel).toBe("V-2026-0142 · Heizung");
    expect(e?.untertitel).toBe("Müller GmbH · 20.11.2026");
    const r = trefferZuEintrag(hit("rechnung", "r1", "R-1", { kunde_name: "Müller", betrag: "2310.40" }), "office");
    expect(r?.untertitel).toMatch(/^Müller · 2\.310,40\s€$/);
  });

  it("formatAnzahl deckelt bei 99+", () => {
    expect(formatAnzahl(99)).toBe("99");
    expect(formatAnzahl(100)).toBe("99+");
  });
});
