// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { holeLoginZiel, istSicheresLoginZiel, loescheLoginZiel, merkeLoginZiel } from "./loginZiel";

beforeEach(() => sessionStorage.clear());

describe("loginZiel", () => {
  it("merkt relative Pfade inklusive Query", () => {
    merkeLoginZiel("/ki-verbinden?anfrage=abc");
    expect(holeLoginZiel()).toBe("/ki-verbinden?anfrage=abc");
    loescheLoginZiel();
    expect(holeLoginZiel()).toBeNull();
  });

  it("lehnt fremde Ziele ab", () => {
    for (const z of ["https://evil.de", "//evil.de", "/\\evil.de", "evil", "/login"]) {
      expect(istSicheresLoginZiel(z)).toBe(false);
    }
    merkeLoginZiel("//evil.de");
    expect(holeLoginZiel()).toBeNull();
  });
});
