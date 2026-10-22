// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LadefehlerGrenze, SeitenRahmen, istLadefehler, lazyMitRetry } from "./Nachladen";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function Werfer({ fehler }: { fehler: Error }): never {
  throw fehler;
}

describe("istLadefehler", () => {
  it("erkennt die Meldungen der gaengigen Browser", () => {
    expect(istLadefehler(new TypeError("Failed to fetch dynamically imported module: /assets/X-1.js"))).toBe(true);
    expect(istLadefehler(new TypeError("error loading dynamically imported module"))).toBe(true);
    expect(istLadefehler(new TypeError("Importing a module script failed."))).toBe(true);
    const chunk = new Error("Loading chunk 7 failed");
    chunk.name = "ChunkLoadError";
    expect(istLadefehler(chunk)).toBe(true);
  });

  it("laesst andere Fehler aus", () => {
    expect(istLadefehler(new Error("Cannot read properties of undefined"))).toBe(false);
  });
});

describe("LadefehlerGrenze", () => {
  it("zeigt bei Ladefehler den Neuladen-Hinweis", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    render(
      <LadefehlerGrenze>
        <Werfer fehler={new TypeError("Failed to fetch dynamically imported module: /a.js")} />
      </LadefehlerGrenze>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Diese Seite konnte nicht geladen werden");
    expect(screen.getByRole("button", { name: "Seite neu laden" })).toBeInTheDocument();
  });

  it("reicht fremde Fehler weiter statt sie zu verschlucken", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() =>
      render(
        <LadefehlerGrenze>
          <Werfer fehler={new Error("Logikfehler")} />
        </LadefehlerGrenze>,
      ),
    ).toThrow("Logikfehler");
  });
});

describe("lazyMitRetry / SeitenRahmen", () => {
  it("zeigt den ruhigen Fallback und danach die Seite", async () => {
    const Seite = lazyMitRetry(async () => ({ default: () => <p>Fertig geladen</p> }));
    render(
      <MemoryRouter>
        <SeitenRahmen>
          <Seite />
        </SeitenRahmen>
      </MemoryRouter>,
    );
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByText("Fertig geladen")).toBeInTheDocument();
  });

  it("versucht es nach einem kurzen Fehlschlag erneut", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let versuche = 0;
    const Seite = lazyMitRetry(async () => {
      versuche++;
      if (versuche < 2) throw new TypeError("Failed to fetch dynamically imported module");
      return { default: () => <p>Zweiter Versuch</p> };
    });
    render(
      <MemoryRouter>
        <SeitenRahmen>
          <Seite />
        </SeitenRahmen>
      </MemoryRouter>,
    );
    await vi.advanceTimersByTimeAsync(500);
    expect(await screen.findByText("Zweiter Versuch")).toBeInTheDocument();
    expect(versuche).toBe(2);
  });

  it("meldet nach drei Fehlversuchen den Neuladen-Hinweis", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const Seite = lazyMitRetry(async () => {
      throw new TypeError("Failed to fetch dynamically imported module");
    });
    render(
      <MemoryRouter>
        <SeitenRahmen>
          <Seite />
        </SeitenRahmen>
      </MemoryRouter>,
    );
    await vi.advanceTimersByTimeAsync(2000);
    expect(await screen.findByRole("alert")).toHaveTextContent("neu laden", { normalizeWhitespace: true });
  });
});
