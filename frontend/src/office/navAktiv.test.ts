import { describe, expect, it } from "vitest";

import { NAV_SEITEN } from "../config/navSeiten";
import { aktiverNavKey, fuerOffice } from "./navAktiv";

const alleRechte = () => true;
const seiten = fuerOffice(NAV_SEITEN, {
  currentUser: undefined,
  hatRecht: alleRechte,
});

describe("aktiverNavKey", () => {
  it("markiert die Vorgangsliste und ihre Detailseiten", () => {
    expect(aktiverNavKey("/vorgaenge", seiten)).toBe("feed");
    expect(aktiverNavKey("/vorgaenge/abc", seiten)).toBe("feed");
    expect(aktiverNavKey("/neu", seiten)).toBe("feed");
  });

  it("markiert Unterseiten unter dem Eintrag, zu dem sie gehören", () => {
    expect(aktiverNavKey("/rechnungen/1", seiten)).toBe("rechnungen");
    expect(aktiverNavKey("/angebote/1", seiten)).toBe("rechnungen");
    expect(aktiverNavKey("/formulare/1", seiten)).toBe("formulare");
  });

  it("markiert Kunden und Material samt Detail-URL und Unterseiten", () => {
    expect(aktiverNavKey("/kunden/abc", seiten)).toBe("kunden");
    expect(aktiverNavKey("/standorte/1", seiten)).toBe("kunden");
    expect(aktiverNavKey("/material", seiten)).toBe("material");
    expect(aktiverNavKey("/bestellungen/1", seiten)).toBe("geschaeft");
  });

  it("verwechselt Präfixe nicht", () => {
    expect(aktiverNavKey("/rechnungseingang", seiten)).toBe("rechnungseingang");
  });

  it("gibt null zurück, wenn nichts passt", () => {
    expect(aktiverNavKey("/suche", seiten)).toBeNull();
  });
});
