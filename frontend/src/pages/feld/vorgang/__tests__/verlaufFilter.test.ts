import { describe, expect, it } from "vitest";

import type { OutboxItem } from "../../../../offline/db";
import type { VorgangEvent } from "../../../../types";
import type { VerlaufEintrag } from "../konstanten";
import { VERLAUF_FILTER_OPTIONEN, outboxItemPasst, verlaufEintragPasst } from "../verlaufFilter";

function eintrag(event_type: VorgangEvent["event_type"], is_system = false): VerlaufEintrag {
  return { art: "event", zeit: "2026-11-18T10:00:00Z", event: { event_type, is_system } as VorgangEvent };
}
const email: VerlaufEintrag = { art: "email", zeit: "2026-11-18T10:00:00Z", email: {} as never };

describe("Verlaufsfilter Telefonate", () => {
  it("steht zwischen Kommentare und E-Mail", () => {
    expect(VERLAUF_FILTER_OPTIONEN.map((o) => o.label)).toEqual(["Alle", "Kommentare", "Telefonate", "E-Mail", "System"]);
  });

  it("zeigt unter Telefonate nur Telefonate", () => {
    expect(verlaufEintragPasst(eintrag("telefonat"), "telefonate")).toBe(true);
    expect(verlaufEintragPasst(eintrag("kommentar"), "telefonate")).toBe(false);
    expect(verlaufEintragPasst(email, "telefonate")).toBe(false);
  });

  it("zählt Telefonate weder zu Kommentare noch zu System", () => {
    expect(verlaufEintragPasst(eintrag("telefonat"), "kommentare")).toBe(false);
    expect(verlaufEintragPasst(eintrag("telefonat"), "system")).toBe(false);
    expect(verlaufEintragPasst(eintrag("telefonat"), "alle")).toBe(true);
    expect(verlaufEintragPasst(eintrag("telefonat"), "email")).toBe(false);
  });

  it("lässt die übrigen Filter unverändert", () => {
    expect(verlaufEintragPasst(eintrag("kommentar"), "kommentare")).toBe(true);
    expect(verlaufEintragPasst(eintrag("foto"), "kommentare")).toBe(true);
    expect(verlaufEintragPasst(eintrag("status_change"), "system")).toBe(true);
    expect(verlaufEintragPasst(eintrag("status_change"), "kommentare")).toBe(false);
    expect(verlaufEintragPasst(email, "email")).toBe(true);
    expect(verlaufEintragPasst(email, "kommentare")).toBe(false);
  });

  it("ordnet ausstehende Outbox-Telefonate nur dem Telefonate-Filter zu", () => {
    const item = (kind: OutboxItem["kind"]) => ({ kind }) as OutboxItem;
    expect(outboxItemPasst(item("telefonat"), "telefonate")).toBe(true);
    expect(outboxItemPasst(item("telefonat"), "kommentare")).toBe(false);
    expect(outboxItemPasst(item("telefonat"), "system")).toBe(false);
    expect(outboxItemPasst(item("kommentar"), "telefonate")).toBe(false);
    expect(outboxItemPasst(item("kommentar"), "kommentare")).toBe(true);
  });
});
