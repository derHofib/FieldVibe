import { describe, expect, it } from "vitest";

import type { FehlerberichtKontext, Kategorie } from "../../index";
import { baueFormular, fehlerText, type FormularWerte } from "../payload";

const kontext: FehlerberichtKontext = {
  netzwerk: [{ zeit: "z", methode: "GET", url: "/x", status: 500, dauer_ms: 1 }],
  konsole: [{ zeit: "z", level: "error", nachricht: "boom" }],
  breadcrumbs: [{ zeit: "z", typ: "klick", ziel: "button" }],
  sitzung: { rolle: "admin" },
  app_state: { filter: "a" },
};
const werte: FormularWerte = { titel: " Titel ", beschreibung: "Text", erwartet: "", schritte: "1. x", schweregrad: "mittel" };
const alle = new Set<Kategorie>(["netzwerk", "konsole", "breadcrumbs", "sitzung", "app_state"]);

function payloadVon(fd: FormData) {
  return JSON.parse(fd.get("payload") as string);
}

describe("baueFormular", () => {
  it("lässt abgewählte Kategorien im Kontext weg", () => {
    const fd = baueFormular({ werte, kontext, auswahl: new Set<Kategorie>(["konsole"]), screenshot: null });
    expect(Object.keys(payloadVon(fd).kontext)).toEqual(["konsole"]);
  });

  it("sendet ohne Screenshot keine Dateien", () => {
    const fd = baueFormular({ werte, kontext, auswahl: alle, screenshot: null });
    expect(fd.has("screenshot_original")).toBe(false);
    expect(fd.has("screenshot_annotiert")).toBe(false);
  });

  it("hängt beide Bilder an, wenn ein Screenshot vorliegt", () => {
    const blob = new Blob(["x"], { type: "image/png" });
    const fd = baueFormular({ werte, kontext, auswahl: alle, screenshot: { original: blob, annotiert: blob } });
    expect(fd.get("screenshot_original")).toBeInstanceOf(File);
    expect(fd.get("screenshot_annotiert")).toBeInstanceOf(File);
  });

  it("trimmt Pflichtfelder, lässt leere optionale Felder weg und übernimmt Metadaten", () => {
    const p = payloadVon(
      baueFormular({ werte, kontext, auswahl: alle, screenshot: null, route: "/feed", appVersion: "1", commitSha: "abc" }),
    );
    expect(p).toMatchObject({ titel: "Titel", schweregrad: "mittel", schritte: "1. x", route: "/feed", app_version: "1", commit_sha: "abc" });
    expect(p).not.toHaveProperty("erwartet");
  });
});

describe("fehlerText", () => {
  it("unterscheidet Limit, Größe und Netzwerkfehler", () => {
    expect(fehlerText({ status: 429 })).toMatch(/Zu viele/);
    expect(fehlerText({ status: 413 })).toMatch(/zu groß/);
    expect(fehlerText(new TypeError("Failed to fetch"))).toMatch(/Keine Verbindung/);
    expect(fehlerText({ status: 500, message: "Oje" })).toContain("Oje");
  });
});
