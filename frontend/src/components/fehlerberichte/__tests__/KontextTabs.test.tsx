// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { FehlerberichtKontext } from "../../../bugreport/typen";
import { KontextTabs } from "../KontextTabs";

afterEach(cleanup);

const kontext: FehlerberichtKontext = {
  netzwerk: [
    { zeit: "2026-10-04T10:00:00Z", methode: "GET", url: "/api/ok", status: 200, dauer_ms: 12 },
    {
      zeit: "2026-10-04T10:00:01Z",
      methode: "POST",
      url: "/api/kaputt",
      status: 500,
      dauer_ms: 40,
      response_body: '{"detail":"boom"}',
      response_headers: { "content-type": "application/json" },
    },
    { zeit: "2026-10-04T10:00:02Z", methode: "GET", url: "/api/offline", status: 0, dauer_ms: 1, fehler: "Failed to fetch" },
  ],
  konsole: [
    { zeit: "2026-10-04T10:00:00Z", level: "error", nachricht: "Kaputt", stack: "at foo (bar.js:1)" },
    { zeit: "2026-10-04T10:00:00Z", level: "warn", nachricht: "Achtung" },
  ],
  breadcrumbs: [{ zeit: "2026-10-04T10:00:00Z", typ: "klick", ziel: "button#speichern", text: "Speichern" }],
  umgebung: { url: "https://x", plattform: "Linux" } as FehlerberichtKontext["umgebung"],
  sitzung: { rolle: "mandant_admin" },
  app_state: { filter: { status: "offen" } },
};

describe("KontextTabs", () => {
  it("zeigt den Klickpfad als Standard-Tab", () => {
    render(<KontextTabs kontext={kontext} />);
    expect(screen.getByText("button#speichern", { exact: false })).toBeTruthy();
  });

  it("hebt fehlgeschlagene Requests (status >= 400 oder fehler) hervor und klappt Details auf", () => {
    const { container } = render(<KontextTabs kontext={kontext} />);
    fireEvent.click(screen.getByRole("button", { name: /Netzwerk/ }));
    const zeilen = Array.from(container.querySelectorAll("li[data-fehlgeschlagen]"));
    expect(zeilen.map((z) => z.getAttribute("data-fehlgeschlagen"))).toEqual(["false", "true", "true"]);
    expect(zeilen[1].className).toContain("bg-st-fehlt-bg");
    expect(zeilen[0].className).not.toContain("bg-st-fehlt-bg");

    expect(screen.queryByText('{"detail":"boom"}')).toBeNull();
    fireEvent.click(zeilen[1].querySelector("button")!);
    expect(screen.getByText('{"detail":"boom"}')).toBeTruthy();
    expect(screen.getByText("content-type: application/json")).toBeTruthy();
  });

  it("färbt error/warn in der Konsole und klappt den Stack auf", () => {
    const { container } = render(<KontextTabs kontext={kontext} />);
    fireEvent.click(screen.getByRole("button", { name: /Konsole/ }));
    expect(container.querySelector('li[data-level="error"]')!.className).toContain("st-fehlt");
    expect(container.querySelector('li[data-level="warn"]')!.className).toContain("st-arbeit");
    fireEvent.click(screen.getByText("Stack anzeigen"));
    expect(screen.getByText("at foo (bar.js:1)")).toBeTruthy();
  });

  it("zeigt Umgebung inkl. Sitzung und App-State", () => {
    render(<KontextTabs kontext={kontext} />);
    fireEvent.click(screen.getByRole("button", { name: "Umgebung" }));
    expect(screen.getByText("plattform")).toBeTruthy();
    expect(screen.getByText("mandant_admin")).toBeTruthy();
    expect(screen.getByText("filter")).toBeTruthy();
  });

  it.each([{ label: "leerer Kontext", wert: {} }, { label: "null", wert: null }, { label: "undefined", wert: undefined }])(
    "crasht bei fehlenden Kategorien nicht ($label)",
    ({ wert }) => {
      render(<KontextTabs kontext={wert} />);
      expect(screen.getByText("Kein Klickpfad mitgesendet.")).toBeTruthy();
      for (const [tab, text] of [
        [/Netzwerk/, "Keine Netzwerk-Requests mitgesendet."],
        [/Konsole/, "Keine Konsolen-Einträge mitgesendet."],
        [/Umgebung/, "Keine Umgebungsdaten mitgesendet."],
      ] as const) {
        fireEvent.click(screen.getByRole("button", { name: tab }));
        expect(screen.getByText(text)).toBeTruthy();
      }
    },
  );

  it("crasht auch bei falsch typisierten Kategorien nicht", () => {
    render(<KontextTabs kontext={{ netzwerk: "kaputt", konsole: 5, umgebung: [] } as unknown as FehlerberichtKontext} />);
    fireEvent.click(screen.getByRole("button", { name: /Netzwerk/ }));
    expect(screen.getByText("Keine Netzwerk-Requests mitgesendet.")).toBeTruthy();
  });
});
