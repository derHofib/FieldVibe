// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { SlaInfo } from "../types";
import { SlaBadge, formatRestzeit, naechsteSlaFrist } from "./SlaBadge";

const JETZT = new Date("2026-11-01T10:00:00Z").getTime();
const basis: SlaInfo = {
  status: "ok",
  reaktion_faellig_am: "2026-11-01T10:30:00Z",
  loesung_faellig_am: "2026-11-01T14:00:00Z",
  reagiert_am: null,
  geloest_am: null,
  reaktion_ergebnis: null,
  loesung_ergebnis: null,
};

describe("SlaBadge", () => {
  afterEach(cleanup);

  it("formatiert Restzeit und Überfälligkeit", () => {
    expect(formatRestzeit(JETZT + 30 * 60000, JETZT)).toBe("noch 30 Min.");
    expect(formatRestzeit(JETZT + 135 * 60000, JETZT)).toBe("noch 2 Std. 15 Min.");
    expect(formatRestzeit(JETZT - 10 * 60000, JETZT)).toBe("10 Min. überfällig");
  });

  it("nimmt nach der Reaktion die Lösungsfrist", () => {
    expect(naechsteSlaFrist(basis)).toBe(basis.reaktion_faellig_am);
    expect(naechsteSlaFrist({ ...basis, reagiert_am: "2026-11-01T10:05:00Z" })).toBe(basis.loesung_faellig_am);
  });

  it("zeigt Status als Text, nicht nur als Farbe", () => {
    render(<SlaBadge sla={{ ...basis, status: "gefaehrdet" }} jetzt={JETZT} />);
    expect(screen.getByText(/SLA gefährdet/)).toBeTruthy();
    expect(screen.getByText(/noch 30 Min\./)).toBeTruthy();
  });

  it("rendert ohne SLA nichts", () => {
    const { container } = render(<SlaBadge sla={null} />);
    expect(container.firstChild).toBeNull();
  });
});
