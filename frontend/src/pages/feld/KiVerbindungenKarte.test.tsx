// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "../../types";
import { ProfilePage } from "./ProfilePage";

const verbindungen = vi.fn();
const trennen = vi.fn();
vi.mock("../../api/endpoints", () => ({
  kiApi: { verbindungen: (...a: unknown[]) => verbindungen(...a), trennen: (...a: unknown[]) => trennen(...a) },
  authApi: {},
}));
vi.mock("./MfaKarte", () => ({ MfaKarte: () => null }));
vi.mock("./PasswortAendernKarte", () => ({ PasswortAendernKarte: () => null }));
vi.mock("./ProfilUebersichten", () => ({
  ProfilArbeitszeitKarte: () => null,
  ProfilUrlaubKarte: () => null,
  ProfilVorgaengeKarte: () => null,
}));
vi.mock("../../components/AppearancePicker", () => ({ AppearancePicker: () => null }));

let nutzer: Partial<CurrentUser>;
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: nutzer, hatRecht: () => false, isImpersonating: false, logout: vi.fn() }),
}));

function rendern() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProfilePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const eintrag = {
  id: "v1",
  client_name: "Claude",
  scopes: ["fieldvibe.lesen"],
  user_id: "u1",
  user_name: "Erika Muster",
  erstellt_am: "2026-11-01T10:00:00Z",
  zuletzt_genutzt_am: null,
};

beforeEach(() => {
  verbindungen.mockReset();
  trennen.mockReset();
  nutzer = { role: "custom", name: "Max", email: "m@x.de", mandant_name: "Betrieb", deaktivierte_module: [] };
});
afterEach(cleanup);

describe("KI-Verbindungen im Profil", () => {
  it("listet Verbindungen und trennt nach Bestätigung", async () => {
    verbindungen.mockResolvedValue([eintrag]);
    trennen.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    rendern();
    expect(await screen.findByText("Claude")).toBeInTheDocument();
    expect(screen.getByText(/Nur lesen/)).toBeInTheDocument();
    expect(screen.getByText(/noch nicht genutzt/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Claude trennen" }));
    await waitFor(() => expect(trennen).toHaveBeenCalledWith("v1"));
  });

  it("trennt nicht, wenn die Bestätigung abgelehnt wird", async () => {
    verbindungen.mockResolvedValue([eintrag]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    rendern();
    fireEvent.click(await screen.findByRole("button", { name: "Claude trennen" }));
    await new Promise((r) => setTimeout(r, 10));
    expect(trennen).not.toHaveBeenCalled();
  });

  it("zeigt im Leerzustand die Connector-URL", async () => {
    verbindungen.mockResolvedValue([]);
    rendern();
    expect(await screen.findByText(/Keine aktive Verbindung/)).toBeInTheDocument();
    expect(screen.getByText(/\/mcp$/)).toBeInTheDocument();
  });

  it("blendet den Abschnitt bei deaktiviertem Modul aus", () => {
    nutzer = { ...nutzer, deaktivierte_module: ["ki_zugriff"] };
    rendern();
    expect(screen.queryByText("KI-Verbindungen")).not.toBeInTheDocument();
    expect(verbindungen).not.toHaveBeenCalled();
  });

  it("zeigt dem Mandant-Admin den Umschalter und lädt mit alle=true", async () => {
    nutzer = { ...nutzer, role: "mandant_admin" };
    verbindungen.mockResolvedValue([eintrag]);
    rendern();
    await screen.findByText("Claude");
    fireEvent.click(screen.getByLabelText("Alle im Betrieb anzeigen"));
    await waitFor(() => expect(verbindungen).toHaveBeenCalledWith(true));
    expect(await screen.findByText(/Erika Muster/)).toBeInTheDocument();
  });

  it("zeigt anderen Rollen keinen Umschalter", async () => {
    verbindungen.mockResolvedValue([]);
    rendern();
    await screen.findByText(/Keine aktive Verbindung/);
    expect(screen.queryByLabelText("Alle im Betrieb anzeigen")).not.toBeInTheDocument();
  });
});
