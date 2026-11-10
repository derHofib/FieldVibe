import { describe, expect, it } from "vitest";

import type { Einladung, PartnerZugang } from "../types";
import { einladungFehlerText, partnerPortalLink, portalZugangStatus } from "./partnerZugang";

const zugang = (p: Partial<PartnerZugang> = {}): PartnerZugang => ({
  id: "z1",
  partner_id: "p1",
  email: "a@b.de",
  name: "A",
  aktiv: true,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  ...p,
});
const einladung = (p: Partial<Einladung> = {}): Einladung => ({
  id: "e1",
  email: "a@b.de",
  art: "partner",
  rolle: null,
  account_typ_id: null,
  kunde_id: null,
  partner_id: "p1",
  status: "offen",
  abgelaufen: false,
  created_at: "2026-09-01T10:00:00Z",
  angenommen_am: null,
  registrierungslink: null,
  ...p,
});

describe("portalZugangStatus", () => {
  it("ohne alles: keiner", () => expect(portalZugangStatus([], []).art).toBe("keiner"));
  it("widerrufene Einladung zählt nicht", () =>
    expect(portalZugangStatus([], [einladung({ status: "widerrufen" })]).art).toBe("keiner"));
  it("offene Einladung", () => expect(portalZugangStatus([], [einladung()]).art).toBe("offen"));
  it("abgelaufene offene Einladung", () =>
    expect(portalZugangStatus([], [einladung({ abgelaufen: true })]).art).toBe("abgelaufen"));
  it("Zugang schlägt Einladung", () =>
    expect(portalZugangStatus([zugang()], [einladung({ status: "angenommen" })]).art).toBe("aktiv"));
  it("gesperrter Zugang", () => expect(portalZugangStatus([zugang({ aktiv: false })], []).art).toBe("gesperrt"));
});

describe("Hilfsfunktionen", () => {
  it("Portal-Link ohne doppelten Slash", () =>
    expect(partnerPortalLink("https://x.example.de/")).toBe("https://x.example.de/partnerportal"));
  it("Fehlertexte", () => {
    expect(einladungFehlerText(409, "Für diese E-Mail-Adresse existiert bereits ein Account")).toContain("existiert bereits");
    expect(einladungFehlerText(403, "x")).toContain("Nachunternehmer");
    expect(einladungFehlerText(422, "x")).toContain("gültige E-Mail");
  });
});
