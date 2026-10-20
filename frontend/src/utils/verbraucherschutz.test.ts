import { describe, expect, it } from "vitest";

import {
  firmendatenAusFormular,
  formularAusFirmendaten,
  modusAusFirmendaten,
  portalFormularFehler,
  zeigtPlatzhalterBelehrung,
} from "./verbraucherschutz";

describe("verbraucherschutz", () => {
  it("behandelt fehlenden oder unbekannten Modus als aus (Bestandsmandant)", () => {
    expect(modusAusFirmendaten({})).toBe("aus");
    expect(modusAusFirmendaten({ portal_verbraucherschutz: "nur_privatkunden" })).toBe("nur_privatkunden");
    // @ts-expect-error absichtlich ungueltiger Wert aus alten Daten
    expect(modusAusFirmendaten({ portal_verbraucherschutz: "immer" })).toBe("aus");
  });

  it("warnt nur bei aktivem Schutz ohne eigenen Belehrungstext", () => {
    expect(zeigtPlatzhalterBelehrung("aus", "")).toBe(false);
    expect(zeigtPlatzhalterBelehrung("nur_privatkunden", "   ")).toBe(true);
    expect(zeigtPlatzhalterBelehrung("nur_privatkunden", undefined)).toBe(true);
    expect(zeigtPlatzhalterBelehrung("nur_privatkunden", "Text")).toBe(false);
  });

  it("sendet nur die Portal-Schluessel, getrimmt", () => {
    const f = formularAusFirmendaten({ impressum_url: "https://x.de", portal_verbraucherschutz: "nur_privatkunden" });
    const payload = firmendatenAusFormular({ ...f, belehrungText: "  Text ", belehrungVersion: " 2026-10 " });
    expect(payload).toEqual({
      portal_verbraucherschutz: "nur_privatkunden",
      widerrufsbelehrung_text: "Text",
      widerrufsbelehrung_version: "2026-10",
      barrierefreiheit_kontakt_email: "",
      barrierefreiheit_stand: "",
      barrierefreiheit_url: "",
    });
    expect(payload).not.toHaveProperty("impressum_url");
  });

  it("validiert E-Mail und URL wie das Backend", () => {
    const basis = formularAusFirmendaten({});
    expect(portalFormularFehler(basis)).toEqual({});
    expect(portalFormularFehler({ ...basis, barrierefreiheitEmail: "keine-mail" }).barrierefreiheitEmail).toBeTruthy();
    expect(portalFormularFehler({ ...basis, barrierefreiheitUrl: "javascript:alert(1)" }).barrierefreiheitUrl).toBeTruthy();
    expect(portalFormularFehler({ ...basis, barrierefreiheitEmail: "a@b.de", barrierefreiheitUrl: "https://b.de" })).toEqual({});
  });
});
