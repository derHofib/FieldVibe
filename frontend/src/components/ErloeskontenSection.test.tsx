// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen } from "../types";
import { ErloeskontenSection } from "./ErloeskontenSection";

vi.mock("../api/endpoints", () => ({ mandantEinstellungenApi: { firmendatenSpeichern: vi.fn() } }));

const einstellungen = {
  firmendaten: {
    ust_idnr: "DE1",
    impressum_url: "https://example.de/impressum",
    unbekannt: "bleibt",
    buchhaltung: { erloeskonten: { "S:19.00": { konto: "8400", bu: "" } } },
  },
} as unknown as MandantEinstellungen;

function renderSektion() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ErloeskontenSection einstellungen={einstellungen} />
    </QueryClientProvider>,
  );
}

function felder(label: RegExp) {
  return screen.getAllByLabelText(label) as HTMLInputElement[];
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ErloeskontenSection", () => {
  it("zeigt die fünf Zeilen mit dem Hilfetext und den gespeicherten Konten", () => {
    renderSektion();
    expect(felder(/^Konto$/)).toHaveLength(5);
    expect(felder(/^Konto$/)[0]).toHaveValue("8400");
    expect(screen.getByText(/Standardkonten 8400\/8300/)).toBeInTheDocument();
    expect(screen.getByText("Reverse Charge (§ 13b UStG)")).toBeInTheDocument();
  });

  it("sperrt Speichern bei ungültigem Konto (3 Ziffern) und BU (4 Ziffern)", () => {
    renderSektion();
    const speichern = screen.getByRole("button", { name: "Speichern" });
    const [, , , , ae] = felder(/^Konto$/);
    fireEvent.change(ae, { target: { value: "833" } });
    fireEvent.blur(ae);
    expect(speichern).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Konto: 4 bis 8 Ziffern");

    fireEvent.change(ae, { target: { value: "8337" } });
    expect(speichern).toBeEnabled();
    // maxLength=3 verhindert die Eingabe im Browser; jsdom erzwingt das beim programmatischen Setzen nicht.
    fireEvent.change(felder(/BU-Schlüssel/)[4], { target: { value: "1234" } });
    expect(speichern).toBeDisabled();
  });

  it("sendet die vollständige Tabelle ohne leere Zeilen und behält die übrigen Firmendaten", async () => {
    vi.mocked(mandantEinstellungenApi.firmendatenSpeichern).mockResolvedValue(einstellungen);
    renderSektion();
    fireEvent.change(felder(/^Konto$/)[4], { target: { value: "8337" } });
    fireEvent.change(felder(/BU-Schlüssel/)[4], { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(mandantEinstellungenApi.firmendatenSpeichern).toHaveBeenCalledTimes(1));
    expect(mandantEinstellungenApi.firmendatenSpeichern).toHaveBeenCalledWith({
      ust_idnr: "DE1",
      impressum_url: "https://example.de/impressum",
      unbekannt: "bleibt",
      buchhaltung: {
        erloeskonten: {
          "S:19.00": { konto: "8400", bu: "" },
          "AE:0.00": { konto: "8337", bu: "9" },
        },
      },
    });
  });
});
