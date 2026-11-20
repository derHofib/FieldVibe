import { describe, expect, it } from "vitest";

import type { CurrentUser, RechteAktion, RechteBereich } from "../types";
import { sichtbareNavSeiten } from "./navSeiten";

function sichtbar(deaktiviert: string[], rechte: Partial<Record<RechteBereich, RechteAktion[]>>): boolean {
  const currentUser = { role: "mandant_admin", rechte, deaktivierte_module: deaktiviert } as unknown as CurrentUser;
  const hatRecht = (b: RechteBereich, a: RechteAktion) => rechte[b]?.includes(a) ?? false;
  return sichtbareNavSeiten(currentUser, hatRecht).some((s) => s.key === "ki_aktivitaet");
}

describe("Nav-Eintrag KI-Aktivität", () => {
  it("braucht aktives Modul ki_zugriff und das Recht ki_zugriff.sehen", () => {
    expect(sichtbar([], { ki_zugriff: ["sehen"] })).toBe(true);
    expect(sichtbar([], {})).toBe(false);
    expect(sichtbar(["ki_zugriff"], { ki_zugriff: ["sehen"] })).toBe(false);
  });
});
