// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RechtlicheLinks } from "./RechtlicheLinks";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("RechtlicheLinks", () => {
  it("rendert beide Links mit gesetzter Env", () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "https://example.de/impressum");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "https://example.de/datenschutz");

    render(<RechtlicheLinks />);

    const impressum = screen.getByRole("link", { name: "Impressum" });
    expect(impressum).toHaveAttribute("href", "https://example.de/impressum");
    expect(impressum).toHaveAttribute("target", "_blank");
    expect(impressum).toHaveAttribute("rel", "noopener noreferrer");
    const datenschutz = screen.getByRole("link", { name: "Datenschutz" });
    expect(datenschutz).toHaveAttribute("href", "https://example.de/datenschutz");
    expect(datenschutz).toHaveAttribute("target", "_blank");
    expect(datenschutz).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("rendert in Produktion nichts bei leeren URLs", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "   ");

    const { container } = render(<RechtlicheLinks />);

    expect(container).toBeEmptyDOMElement();
  });

  it("rendert in Produktion nur den gesetzten Link", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_IMPRESSUM_URL", "https://example.de/impressum");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");

    render(<RechtlicheLinks />);

    expect(screen.getByRole("link", { name: "Impressum" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Datenschutz" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Datenschutz/)).not.toBeInTheDocument();
  });

  it("zeigt in der Entwicklung einen Platzhalter statt eines Links", () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");

    render(<RechtlicheLinks />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Impressum (URL fehlt)")).toBeInTheDocument();
    expect(screen.getByText("Datenschutz (URL fehlt)")).toBeInTheDocument();
  });
});
