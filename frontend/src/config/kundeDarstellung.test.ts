import { describe, expect, it } from "vitest";

import { kundeTypLabel } from "./kundeDarstellung";

describe("kundeTypLabel", () => {
  it("schreibt bekannte Typen groß", () => {
    expect(kundeTypLabel("gewerbe")).toBe("Gewerbe");
    expect(kundeTypLabel("hausverwaltung")).toBe("Hausverwaltung");
  });
  it("macht unbekannte Typen lesbar", () => {
    expect(kundeTypLabel("wohn_gemeinschaft")).toBe("Wohn gemeinschaft");
  });
});
