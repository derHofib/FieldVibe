import { describe, expect, it } from "vitest";

import { NAV_SEITEN, WORKSPACES } from "../config/navSeiten";
import { aktiverNavKey, fuerOffice, workspaceFuerRoute } from "./navAktiv";

const seiten = fuerOffice(NAV_SEITEN);
const seite = (key: string) => seiten.find((s) => s.key === key);

describe("aktiverNavKey", () => {
  it("markiert die Vorgangsliste und ihre Detailseiten", () => {
    expect(aktiverNavKey("/vorgaenge", seiten)).toBe("feed");
    expect(aktiverNavKey("/vorgaenge/abc", seiten)).toBe("feed");
    expect(aktiverNavKey("/neu", seiten)).toBe("feed");
  });

  it("markiert Unterseiten unter dem Eintrag, zu dem sie gehören", () => {
    expect(aktiverNavKey("/rechnungen/1", seiten)).toBe("rechnungen");
    expect(aktiverNavKey("/angebote/1", seiten)).toBe("rechnungen");
    expect(aktiverNavKey("/kunden/abc", seiten)).toBe("kunden");
    expect(aktiverNavKey("/standorte/1", seiten)).toBe("kunden");
    expect(aktiverNavKey("/bestellungen/1", seiten)).toBe("material");
  });

  it("verwechselt Präfixe nicht", () => {
    expect(aktiverNavKey("/rechnungseingang", seiten)).toBe("rechnungseingang");
  });

  it("gibt null zurück, wenn nichts passt", () => {
    expect(aktiverNavKey("/suche", seiten)).toBeNull();
  });
});

describe("workspaceFuerRoute", () => {
  it("wählt den Workspace der Seite, auch wenn ein anderer gemerkt ist", () => {
    expect(workspaceFuerRoute(seite("rechnungen"), WORKSPACES, "operativ")?.key).toBe("finanzen");
    expect(workspaceFuerRoute(seite("kunden"), WORKSPACES, null)?.key).toBe("sales");
  });

  it("behält den gemerkten Workspace bei Seiten, die in mehreren liegen", () => {
    expect(workspaceFuerRoute(seite("kennzahlen"), WORKSPACES, "finanzen")?.key).toBe("finanzen");
    expect(workspaceFuerRoute(seite("kennzahlen"), WORKSPACES, "sales")?.key).toBe("sales");
  });

  it("behält den gemerkten Workspace bei gemeinsamen Seiten und ohne Treffer", () => {
    expect(workspaceFuerRoute(seite("postfach"), WORKSPACES, "finanzen")?.key).toBe("finanzen");
    expect(workspaceFuerRoute(undefined, WORKSPACES, "sales")?.key).toBe("sales");
  });
});
