import { describe, expect, it } from "vitest";

import { aktivitaetLabel, rolleLabel } from "./anzeigeNamen";

describe("anzeigeNamen", () => {
  it("benennt bekannte Rollen", () => {
    expect(rolleLabel("super_admin")).toBe("Super-Admin");
  });
  it("macht unbekannte Rollen lesbar", () => {
    expect(rolleLabel("kunden_leiter")).toBe("Kunden leiter");
    expect(rolleLabel(undefined)).toBe("–");
  });
  it("benennt bekannte Aktionen", () => {
    expect(aktivitaetLabel("login")).toBe("Anmeldung");
  });
  it("macht unbekannte Aktionen lesbar", () => {
    expect(aktivitaetLabel("rechnung_storniert")).toBe("Rechnung storniert");
  });
});
