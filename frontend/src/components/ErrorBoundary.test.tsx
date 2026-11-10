// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

afterEach(cleanup);

function Kaputt(): never {
  throw new Error("kaputt");
}

describe("ErrorBoundary", () => {
  it("zeigt Fallback mit Neu laden statt weisser Seite", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Kaputt />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Neu laden")).toBeInTheDocument();
    // Ohne Berichtsrecht (kein Provider) wird kein Melden-Button angeboten.
    expect(screen.queryByText("Fehler melden")).toBeNull();
    spy.mockRestore();
  });

  it("rendert Kinder unveraendert, wenn nichts schiefgeht", () => {
    render(
      <ErrorBoundary>
        <p>Inhalt</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Inhalt")).toBeInTheDocument();
  });
});
