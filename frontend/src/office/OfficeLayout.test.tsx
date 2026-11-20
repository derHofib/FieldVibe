// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OfficeLayout } from "./OfficeLayout";

vi.mock("../api/endpoints", () => ({
  searchApi: { search: vi.fn(async () => ({ treffer: [], anzahl: {} })) },
  tagsApi: { list: vi.fn(async () => []) },
  navKategorienApi: { get: vi.fn(async () => ({ kategorien: [] })) },
  projekteApi: { list: vi.fn(async () => []) },
  statistikApi: {},
  vorgaengeApi: { list: vi.fn(async () => []) },
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { id: "u1", role: "mandant_admin", deaktivierte_module: [], rechte: [] },
    hatRecht: () => true,
    logout: () => {},
  }),
}));
vi.mock("../bugreport/ui", () => ({ useFehlerbericht: () => ({ verfuegbar: false, aufnehmen: () => {} }) }));
vi.mock("../hooks/useAppLiveDaten", () => ({ useAppLiveDaten: () => ({ outboxCount: 0, isOnline: true }) }));
vi.mock("../hooks/useTelefonate", () => ({ useAnzahlOffeneRueckrufe: () => 0 }));
vi.mock("../hooks/useVorgemerkteZeitenAnzahl", () => ({ useVorgemerkteZeitenAnzahl: () => 0 }));
vi.mock("../components/ThemeToggle", () => ({ ThemeToggle: () => null }));
vi.mock("../components/ImpersonationBanner", () => ({ ImpersonationBanner: () => null }));
vi.mock("../components/ErrorBoundary", () => ({ SeitenGrenze: () => <p>Seiteninhalt</p> }));

function rendere() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/vorgaenge"]}>
        <Routes>
          <Route path="*" element={<OfficeLayout />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);

describe("OfficeLayout: Suchfenster", () => {
  it("Strg+K öffnet das Fenster über der Seite statt zu navigieren, noch einmal schließt es", () => {
    rendere();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog", { name: "Globale Suche" })).toBeInTheDocument();
    expect(screen.getByText("Seiteninhalt")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("„/“ außerhalb von Eingabefeldern und die Lupe öffnen das Fenster", () => {
    rendere();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Suche" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
