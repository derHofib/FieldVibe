import { describe, expect, it } from "vitest";

import { auditLabel } from "./auditLabel";

describe("auditLabel", () => {
  it("macht snake_case lesbar", () => {
    expect(auditLabel("rechnung_storniert")).toBe("Rechnung storniert");
  });
  it("trennt Namensräume mit Punkt", () => {
    expect(auditLabel("mandant.status_geaendert")).toBe("Mandant · status geaendert");
  });
  it("liefert Strich bei leerem Wert", () => {
    expect(auditLabel(null)).toBe("–");
  });
});
