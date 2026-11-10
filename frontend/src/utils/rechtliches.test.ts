import { describe, expect, it } from "vitest";

import { aufloesenRechtlicheUrl, istHttpUrl } from "./rechtliches";

describe("istHttpUrl", () => {
  it("akzeptiert nur http(s) mit Host", () => {
    expect(istHttpUrl("https://example.de/impressum")).toBe(true);
    expect(istHttpUrl("http://example.de")).toBe(true);
    expect(istHttpUrl("  https://example.de  ")).toBe(true);
    expect(istHttpUrl("javascript:alert(1)")).toBe(false);
    expect(istHttpUrl("ftp://example.de")).toBe(false);
    expect(istHttpUrl("//example.de")).toBe(false);
    expect(istHttpUrl("/impressum")).toBe(false);
    expect(istHttpUrl("https://")).toBe(false);
    expect(istHttpUrl("https://exa mple.de")).toBe(false);
    expect(istHttpUrl("")).toBe(false);
    expect(istHttpUrl(null)).toBe(false);
    expect(istHttpUrl(undefined)).toBe(false);
  });
});

describe("aufloesenRechtlicheUrl", () => {
  it("bevorzugt die URL aus den Firmendaten vor der Env", () => {
    expect(
      aufloesenRechtlicheUrl({
        seite: "impressum",
        firmendatenUrl: "https://firma.de/impressum",
        envUrl: "https://env.de/impressum",
      }),
    ).toEqual({ href: "https://firma.de/impressum", extern: true });
  });

  it("nimmt die Env, wenn die Firmendaten keine URL haben", () => {
    expect(
      aufloesenRechtlicheUrl({ seite: "datenschutz", firmendatenUrl: "", envUrl: "https://env.de/ds" }),
    ).toEqual({ href: "https://env.de/ds", extern: true });
    expect(
      aufloesenRechtlicheUrl({ seite: "datenschutz", firmendatenUrl: null, envUrl: " https://env.de/ds " }),
    ).toEqual({ href: "https://env.de/ds", extern: true });
  });

  it("faellt auf die interne Platzhalter-Route zurueck", () => {
    expect(aufloesenRechtlicheUrl({ seite: "impressum" })).toEqual({
      href: "/impressum",
      extern: false,
    });
    expect(aufloesenRechtlicheUrl({ seite: "datenschutz", firmendatenUrl: "  ", envUrl: "  " })).toEqual({
      href: "/datenschutz",
      extern: false,
    });
  });

  it("haengt den Portal-Slug nur an die interne Route an", () => {
    expect(aufloesenRechtlicheUrl({ seite: "impressum", portalSlug: "a/b c" })).toEqual({
      href: "/impressum?portal_slug=a%2Fb%20c",
      extern: false,
    });
    expect(
      aufloesenRechtlicheUrl({ seite: "impressum", firmendatenUrl: "https://f.de", portalSlug: "abc" }).href,
    ).toBe("https://f.de");
  });

  it("verwirft nicht-http-Werte und faellt weiter durch", () => {
    expect(
      aufloesenRechtlicheUrl({
        seite: "impressum",
        firmendatenUrl: "javascript:alert(1)",
        envUrl: "https://env.de/i",
      }),
    ).toEqual({ href: "https://env.de/i", extern: true });
    expect(
      aufloesenRechtlicheUrl({ seite: "impressum", firmendatenUrl: "javascript:x", envUrl: "data:text/html,x" }),
    ).toEqual({ href: "/impressum", extern: false });
  });
});
