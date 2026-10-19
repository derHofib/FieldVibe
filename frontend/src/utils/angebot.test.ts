import { describe, expect, it } from "vitest";

import { ablaufAnzeige, ablaufText, mwstSatzWert, validierePosition, verschiebePosition } from "./angebot";

describe("verschiebePosition", () => {
  const ids = ["a", "b", "c"];

  it("tauscht mit dem Nachbarn", () => {
    expect(verschiebePosition(ids, 1, -1)).toEqual(["b", "a", "c"]);
    expect(verschiebePosition(ids, 1, 1)).toEqual(["a", "c", "b"]);
  });

  it("lässt die Liste an den Rändern unverändert", () => {
    expect(verschiebePosition(ids, 0, -1)).toBe(ids);
    expect(verschiebePosition(ids, 2, 1)).toBe(ids);
    expect(verschiebePosition(ids, 5, -1)).toBe(ids);
  });

  it("verändert die Eingabe nicht", () => {
    verschiebePosition(ids, 0, 1);
    expect(ids).toEqual(["a", "b", "c"]);
  });
});

describe("mwstSatzWert", () => {
  it("erkennt die drei Sätze auch als Backend-Dezimalstring", () => {
    expect(mwstSatzWert("19.00")).toBe("19");
    expect(mwstSatzWert("7.00")).toBe("7");
    expect(mwstSatzWert("0.00")).toBe("0");
  });

  it("liefert null außerhalb der Auswahl", () => {
    expect(mwstSatzWert("5.00")).toBeNull();
  });
});

describe("ablaufAnzeige", () => {
  const heute = "2026-10-19";
  const versendet = { status: "versendet" as const, ist_abgelaufen: false };

  it("übernimmt abgelaufen aus dem Backend, auch wenn der lokale Tag anders rechnen würde", () => {
    expect(ablaufAnzeige({ ...versendet, ist_abgelaufen: true, gueltig_bis: "2026-10-19" }, heute)).toEqual({
      art: "abgelaufen",
    });
  });

  it("warnt am Tag des Ablaufs und bis zwei Tage davor", () => {
    expect(ablaufAnzeige({ ...versendet, gueltig_bis: "2026-10-19" }, heute)).toEqual({ art: "laeuft_bald_ab", tage: 0 });
    expect(ablaufAnzeige({ ...versendet, gueltig_bis: "2026-10-21" }, heute)).toEqual({ art: "laeuft_bald_ab", tage: 2 });
    expect(ablaufAnzeige({ ...versendet, gueltig_bis: "2026-10-22" }, heute)).toEqual({ art: "keine" });
  });

  it("rechnet über den Monatswechsel", () => {
    expect(ablaufAnzeige({ ...versendet, gueltig_bis: "2026-11-01" }, "2026-10-31")).toEqual({
      art: "laeuft_bald_ab",
      tage: 1,
    });
  });

  it("zeigt nichts ohne Datum und außerhalb von Versendet", () => {
    expect(ablaufAnzeige({ ...versendet, gueltig_bis: null }, heute)).toEqual({ art: "keine" });
    expect(ablaufAnzeige({ status: "entwurf", ist_abgelaufen: false, gueltig_bis: "2026-10-19" }, heute)).toEqual({
      art: "keine",
    });
    expect(ablaufAnzeige({ status: "angenommen", ist_abgelaufen: false, gueltig_bis: "2026-10-19" }, heute)).toEqual({
      art: "keine",
    });
  });
});

describe("ablaufText", () => {
  it("formuliert die Fälle", () => {
    expect(ablaufText({ art: "abgelaufen" })).toBe("Abgelaufen");
    expect(ablaufText({ art: "laeuft_bald_ab", tage: 0 })).toBe("Läuft heute ab");
    expect(ablaufText({ art: "laeuft_bald_ab", tage: 1 })).toBe("Läuft morgen ab");
    expect(ablaufText({ art: "laeuft_bald_ab", tage: 2 })).toBe("Läuft in 2 Tagen ab");
    expect(ablaufText({ art: "keine" })).toBeNull();
  });
});

describe("validierePosition", () => {
  const ok = { beschreibung: "Kabel", menge: "2", einheit: "m", einzelpreis: "1,50" };

  it("akzeptiert gültige Eingaben (auch Komma, Preis 0)", () => {
    expect(validierePosition(ok)).toBeNull();
    expect(validierePosition({ ...ok, einzelpreis: "0" })).toBeNull();
  });

  it("lehnt fehlende und ungültige Werte ab", () => {
    expect(validierePosition({ ...ok, beschreibung: "  " })).toBe("Beschreibung fehlt");
    expect(validierePosition({ ...ok, einheit: "" })).toBe("Einheit fehlt");
    expect(validierePosition({ ...ok, menge: "0" })).toBe("Menge muss größer als 0 sein");
    expect(validierePosition({ ...ok, menge: "" })).toBe("Menge muss größer als 0 sein");
    expect(validierePosition({ ...ok, einzelpreis: "-1" })).toBe("Preis darf nicht negativ sein");
    expect(validierePosition({ ...ok, einzelpreis: "" })).toBe("Preis darf nicht negativ sein");
  });
});
