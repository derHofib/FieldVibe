// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { Rechnung } from "../../types";
import { AbschlagSheet } from "./AbschlagSheet";

vi.mock("../../api/endpoints", () => ({ rechnungenApi: { ausAngebot: vi.fn() } }));

function renderSheet(rest = "1000.00") {
  const onErstellt = vi.fn();
  const onClose = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AbschlagSheet angebotId="a1" angebotNetto="1000.00" restNetto={rest} onClose={onClose} onErstellt={onErstellt} />
    </QueryClientProvider>,
  );
  return { onErstellt, onClose };
}

const erstellen = () => screen.getByRole("button", { name: "Erstellen" });
const eingabe = () => screen.getByLabelText(/Anteil am Angebot/) as HTMLInputElement;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AbschlagSheet", () => {
  it("sperrt Erstellen ohne Eingabe und zeigt die Live-Vorschau für Prozent", () => {
    renderSheet();
    expect(erstellen()).toBeDisabled();
    fireEvent.change(eingabe(), { target: { value: "30" } });
    expect(erstellen()).toBeEnabled();
    const vorschau = screen.getByText("Dieser Abschlag (netto)").parentElement!;
    expect(vorschau).toHaveTextContent(/300,00\s*€/);
    expect(screen.getByText("Rest danach").parentElement).toHaveTextContent(/700,00\s*€/);
  });

  it("meldet Überschreitung des Rests und sperrt Erstellen", () => {
    renderSheet("400.00");
    fireEvent.change(eingabe(), { target: { value: "50" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/mehr als 100 %/);
    expect(erstellen()).toBeDisabled();
  });

  it("sendet im Prozent-Modus abschlag_prozent und optional die Fälligkeit", async () => {
    vi.mocked(rechnungenApi.ausAngebot).mockResolvedValue({ id: "r1" } as Rechnung);
    const { onErstellt } = renderSheet();
    fireEvent.change(eingabe(), { target: { value: "30,5" } });
    fireEvent.change(screen.getByLabelText(/Fällig am/), { target: { value: "2026-11-30" } });
    fireEvent.click(erstellen());
    await waitFor(() => expect(onErstellt).toHaveBeenCalledWith({ id: "r1" }));
    expect(rechnungenApi.ausAngebot).toHaveBeenCalledWith({
      angebot_id: "a1",
      rechnungsart: "abschlag",
      abschlag_prozent: "30.5",
      faellig_am: "2026-11-30",
    });
  });

  it("sendet im Netto-Modus nur abschlag_netto", async () => {
    vi.mocked(rechnungenApi.ausAngebot).mockResolvedValue({ id: "r2" } as Rechnung);
    renderSheet();
    fireEvent.click(screen.getByRole("button", { name: "Nettobetrag" }));
    fireEvent.change(screen.getByLabelText(/Nettobetrag \(EUR\)/), { target: { value: "250,00" } });
    expect(screen.getByText("Rest danach").parentElement).toHaveTextContent(/750,00\s*€/);
    fireEvent.click(erstellen());
    await waitFor(() => expect(rechnungenApi.ausAngebot).toHaveBeenCalled());
    expect(vi.mocked(rechnungenApi.ausAngebot).mock.calls[0][0]).toEqual({
      angebot_id: "a1",
      rechnungsart: "abschlag",
      abschlag_netto: "250.00",
    });
  });

  it("zeigt die Serverfehlermeldung im Sheet", async () => {
    vi.mocked(rechnungenApi.ausAngebot).mockRejectedValue(
      new ApiError(409, "Abschlag AB-1 ist noch nicht versendet"),
    );
    const { onErstellt } = renderSheet();
    fireEvent.change(eingabe(), { target: { value: "10" } });
    fireEvent.click(erstellen());
    expect(await screen.findByText("Abschlag AB-1 ist noch nicht versendet")).toBeInTheDocument();
    expect(onErstellt).not.toHaveBeenCalled();
    expect(erstellen()).toBeEnabled();
  });

  it("sperrt den Button, solange die Anfrage läuft", async () => {
    vi.mocked(rechnungenApi.ausAngebot).mockReturnValue(new Promise(() => {}));
    renderSheet();
    fireEvent.change(eingabe(), { target: { value: "10" } });
    fireEvent.click(erstellen());
    await waitFor(() => expect(erstellen()).toBeDisabled());
  });
});
