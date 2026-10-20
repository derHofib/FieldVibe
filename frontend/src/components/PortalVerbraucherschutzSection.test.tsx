// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen, MandantFirmendaten } from "../types";
import { PortalVerbraucherschutzSection } from "./PortalVerbraucherschutzSection";

vi.mock("../api/endpoints", () => ({ mandantEinstellungenApi: { firmendatenSpeichern: vi.fn() } }));

function einstellungen(firmendaten: MandantFirmendaten): MandantEinstellungen {
  return { firmendaten } as MandantEinstellungen;
}

function renderSektion(firmendaten: MandantFirmendaten) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PortalVerbraucherschutzSection einstellungen={einstellungen(firmendaten)} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PortalVerbraucherschutzSection", () => {
  it("zeigt immer den Hinweis zur rechtlichen Pruefung", () => {
    renderSektion({});
    expect(screen.getByText("Rechtlich prüfen lassen")).toBeInTheDocument();
  });

  it("Bestandsmandant ohne Einstellung steht auf Aus und warnt nicht vor dem Platzhalter", () => {
    renderSektion({});
    expect(screen.getByRole("radio", { name: /^Aus/ })).toBeChecked();
    expect(screen.queryByText("Keine eigene Widerrufsbelehrung hinterlegt")).not.toBeInTheDocument();
  });

  it("warnt bei aktivem Schutz ohne Belehrungstext, nicht mehr mit Text", () => {
    const { unmount } = renderSektion({ portal_verbraucherschutz: "nur_privatkunden" });
    expect(screen.getByText("Keine eigene Widerrufsbelehrung hinterlegt")).toBeInTheDocument();
    unmount();

    renderSektion({ portal_verbraucherschutz: "nur_privatkunden", widerrufsbelehrung_text: "Unser Text" });
    expect(screen.queryByText("Keine eigene Widerrufsbelehrung hinterlegt")).not.toBeInTheDocument();
  });

  it("speichert nur die Portal-Schluessel", async () => {
    vi.mocked(mandantEinstellungenApi.firmendatenSpeichern).mockResolvedValue({} as MandantEinstellungen);
    renderSektion({ impressum_url: "https://x.de" });

    fireEvent.click(screen.getByRole("radio", { name: /Nur für Privatkunden/ }));
    fireEvent.change(screen.getByLabelText("Version / Stand der Belehrung"), { target: { value: "2026-10-19" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(mandantEinstellungenApi.firmendatenSpeichern).toHaveBeenCalled());
    const gesendet = vi.mocked(mandantEinstellungenApi.firmendatenSpeichern).mock.calls[0][0];
    expect(gesendet.portal_verbraucherschutz).toBe("nur_privatkunden");
    expect(gesendet.widerrufsbelehrung_version).toBe("2026-10-19");
    expect(gesendet).not.toHaveProperty("impressum_url");
  });

  it("sperrt Speichern bei ungueltiger Kontakt-E-Mail", () => {
    renderSektion({});
    fireEvent.change(screen.getByLabelText("Kontakt für Feedback (E-Mail)"), { target: { value: "keine-mail" } });
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();
  });
});
