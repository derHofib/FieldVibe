// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen, MandantFirmendaten } from "../types";
import { MfaPflichtSection } from "./MfaPflichtSection";

vi.mock("../api/endpoints", () => ({ mandantEinstellungenApi: { firmendatenSpeichern: vi.fn() } }));

function rendern(firmendaten: MandantFirmendaten) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MfaPflichtSection einstellungen={{ firmendaten } as MandantEinstellungen} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MfaPflichtSection", () => {
  it("steht ohne Eintrag auf aus", () => {
    rendern({});
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it("schaltet ein und sendet nur den mfa_pflicht-Schluessel", async () => {
    vi.mocked(mandantEinstellungenApi.firmendatenSpeichern).mockResolvedValue({} as MandantEinstellungen);
    rendern({ impressum_url: "https://x.de" });
    fireEvent.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(mandantEinstellungenApi.firmendatenSpeichern).toHaveBeenCalledWith({ mfa_pflicht: true }),
    );
  });

  it("zeigt den Zustand an", () => {
    rendern({ mfa_pflicht: true });
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});
