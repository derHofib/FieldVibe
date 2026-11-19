import { describe, expect, it } from "vitest";

import { abgleichStand, allenAntwortenEmpfaenger } from "./postfachHelfer";

describe("allenAntwortenEmpfaenger", () => {
  it("an = Absender, cc = übrige ohne eigene Adresse und ohne Duplikate", () => {
    const r = allenAntwortenEmpfaenger(
      {
        von_adresse: "a@x.de",
        an: ["Ich <ich@y.de>", "b@x.de"],
        cc: ["B@x.de", "c@x.de", "a@x.de"],
      },
      "ich@y.de",
    );
    expect(r.an).toEqual(["a@x.de"]);
    expect(r.cc).toEqual(["b@x.de", "c@x.de"]);
  });
});

describe("abgleichStand", () => {
  it("formatiert Minuten", () => {
    const jetzt = new Date("2026-11-19T10:00:00Z");
    expect(abgleichStand("2026-11-19T09:58:00Z", jetzt)).toBe("Abgeglichen vor 2 Min.");
    expect(abgleichStand(null, jetzt)).toBeNull();
  });
});
