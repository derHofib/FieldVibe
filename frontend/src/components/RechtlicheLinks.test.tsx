// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { rechtlichesApi } from "../api/endpoints";
import type { Rechtliches } from "../types";
import { RechtlicheLinks } from "./RechtlicheLinks";

vi.mock("../api/endpoints", () => ({ rechtlichesApi: { get: vi.fn() } }));

const leer: Rechtliches = { impressum_url: null, datenschutz_url: null, anbieter: null };

function renderLinks(props: Parameters<typeof RechtlicheLinks>[0] = {}, url = "/login") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <RechtlicheLinks {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(rechtlichesApi.get).mockResolvedValue(leer);
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("RechtlicheLinks", () => {
  it("zeigt ohne Env und Firmendaten beide Links auf die Platzhalter-Seiten", () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "   ");

    renderLinks();

    const impressum = screen.getByRole("link", { name: "Impressum" });
    expect(impressum).toHaveAttribute("href", "/impressum");
    expect(impressum).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "Datenschutz" })).toHaveAttribute("href", "/datenschutz");
  });

  it("rendert in Produktion genauso (kein Dev-Platzhalter, nie fehlend)", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");

    renderLinks();

    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.queryByText(/URL fehlt/)).not.toBeInTheDocument();
  });

  it("nutzt die Env-URLs in neuem Tab", () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "https://example.de/impressum");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "https://example.de/datenschutz");

    renderLinks();

    const impressum = screen.getByRole("link", { name: "Impressum" });
    expect(impressum).toHaveAttribute("href", "https://example.de/impressum");
    expect(impressum).toHaveAttribute("target", "_blank");
    expect(impressum).toHaveAttribute("rel", "noopener noreferrer");
    const datenschutz = screen.getByRole("link", { name: "Datenschutz" });
    expect(datenschutz).toHaveAttribute("href", "https://example.de/datenschutz");
    expect(datenschutz).toHaveAttribute("target", "_blank");
    expect(datenschutz).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("gibt den Firmendaten-URLs Vorrang vor der Env, sobald sie geladen sind", async () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "https://env.de/impressum");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");
    vi.mocked(rechtlichesApi.get).mockResolvedValue({
      ...leer,
      impressum_url: "https://firma.de/impressum",
    });

    renderLinks();

    // Sofort vorhanden (Env), danach nachgezogen.
    expect(screen.getByRole("link", { name: "Impressum" })).toHaveAttribute("href", "https://env.de/impressum");
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Impressum" })).toHaveAttribute(
        "href",
        "https://firma.de/impressum",
      ),
    );
    expect(screen.getByRole("link", { name: "Datenschutz" })).toHaveAttribute("href", "/datenschutz");
  });

  it("reicht den Portal-Slug an Abfrage und interne Links durch", async () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");

    renderLinks({ portalSlug: "abc123" });

    expect(screen.getByRole("link", { name: "Impressum" })).toHaveAttribute(
      "href",
      "/impressum?portal_slug=abc123",
    );
    await waitFor(() => expect(rechtlichesApi.get).toHaveBeenCalledWith("abc123"));
  });

  it("liest den Slug aus ?portal_slug= der aktuellen Seite", () => {
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");

    renderLinks({}, "/portal/passwort-vergessen?portal_slug=xyz");

    expect(screen.getByRole("link", { name: "Datenschutz" })).toHaveAttribute(
      "href",
      "/datenschutz?portal_slug=xyz",
    );
  });

  it("bleibt bei Ladefehler bei den Fallback-Links", async () => {
    vi.stubEnv("VITE_IMPRESSUM_URL", "");
    vi.stubEnv("VITE_DATENSCHUTZ_URL", "");
    vi.mocked(rechtlichesApi.get).mockRejectedValue(new Error("offline"));

    renderLinks();

    await waitFor(() => expect(rechtlichesApi.get).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "Impressum" })).toHaveAttribute("href", "/impressum");
  });
});
