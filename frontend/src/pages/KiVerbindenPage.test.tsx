// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { KiVerbindenPage } from "./KiVerbindenPage";

const anfrage = vi.fn();
const autorisieren = vi.fn();
const ablehnen = vi.fn();
vi.mock("../api/endpoints", () => ({
  kiApi: { anfrage: (...a: unknown[]) => anfrage(...a), autorisieren: (...a: unknown[]) => autorisieren(...a), ablehnen: (...a: unknown[]) => ablehnen(...a) },
}));

const assign = vi.fn();

function rendern(url = "/ki-verbinden?anfrage=tok") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <KiVerbindenPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  anfrage.mockReset();
  autorisieren.mockReset();
  ablehnen.mockReset();
  assign.mockReset();
  Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
});
afterEach(cleanup);

const basis = {
  client_name: "Claude",
  scopes_angefragt: ["fieldvibe.lesen", "fieldvibe.schreiben"],
  schreiben_erlaubt: true,
  redirect_host: "claude.ai",
};

describe("KiVerbindenPage", () => {
  it("wählt standardmäßig Nur lesen und autorisiert nur mit Lesen-Scope", async () => {
    anfrage.mockResolvedValue(basis);
    autorisieren.mockResolvedValue({ redirect_url: "https://claude.ai/cb?code=1" });
    rendern();
    expect(await screen.findByText(/Claude möchte auf FieldVibe zugreifen/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Nur lesen/)).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Erlauben" }));
    await waitFor(() => expect(autorisieren).toHaveBeenCalledWith("tok", ["fieldvibe.lesen"]));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://claude.ai/cb?code=1"));
  });

  it("sendet bei Lesen und schreiben beide Scopes", async () => {
    anfrage.mockResolvedValue(basis);
    autorisieren.mockResolvedValue({ redirect_url: "https://claude.ai/cb" });
    rendern();
    fireEvent.click(await screen.findByLabelText(/Lesen und schreiben/));
    fireEvent.click(screen.getByRole("button", { name: "Erlauben" }));
    await waitFor(() => expect(autorisieren).toHaveBeenCalledWith("tok", ["fieldvibe.lesen", "fieldvibe.schreiben"]));
  });

  it("bietet Schreiben nicht an, wenn es nicht erlaubt ist", async () => {
    anfrage.mockResolvedValue({ ...basis, schreiben_erlaubt: false });
    rendern();
    await screen.findByLabelText(/Nur lesen/);
    expect(screen.queryByLabelText(/Lesen und schreiben/)).not.toBeInTheDocument();
  });

  it("bietet Schreiben nicht an, wenn nicht angefragt", async () => {
    anfrage.mockResolvedValue({ ...basis, scopes_angefragt: ["fieldvibe.lesen"] });
    rendern();
    await screen.findByLabelText(/Nur lesen/);
    expect(screen.queryByLabelText(/Lesen und schreiben/)).not.toBeInTheDocument();
  });

  it("lehnt ab und leitet weiter", async () => {
    anfrage.mockResolvedValue(basis);
    ablehnen.mockResolvedValue({ redirect_url: "https://claude.ai/cb?error=access_denied" });
    rendern();
    fireEvent.click(await screen.findByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(ablehnen).toHaveBeenCalledWith("tok"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://claude.ai/cb?error=access_denied"));
    expect(autorisieren).not.toHaveBeenCalled();
  });

  it("zeigt bei 400 einen Fehlerzustand mit Link zur Startseite", async () => {
    anfrage.mockRejectedValue(new ApiError(400, "abgelaufen"));
    rendern();
    expect(await screen.findByText(/ungültig oder abgelaufen/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Startseite" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button", { name: "Erlauben" })).not.toBeInTheDocument();
  });

  it("zeigt bei 403 den Text des Servers", async () => {
    anfrage.mockRejectedValue(new ApiError(403, "KI-Zugriff ist für diesen Betrieb nicht aktiviert."));
    rendern();
    expect(await screen.findByText("KI-Zugriff ist für diesen Betrieb nicht aktiviert.")).toBeInTheDocument();
  });

  it("zeigt ohne Anfrage-Parameter einen Fehlerzustand", async () => {
    rendern("/ki-verbinden");
    expect(await screen.findByText("Anfrage ungültig")).toBeInTheDocument();
    expect(anfrage).not.toHaveBeenCalled();
  });
});
