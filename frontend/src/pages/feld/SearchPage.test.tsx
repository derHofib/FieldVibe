// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchPage } from "./SearchPage";

vi.mock("../../api/endpoints", () => ({
  searchApi: {
    search: vi.fn(async () => ({
      treffer: [
        { kategorie: "kunde", id: "k1", titel: "Müller GmbH", subtitel: null, nummer: "K-1" },
        { kategorie: "auftrag", id: "a1", titel: "Müller Auftrag", subtitel: null },
        { kategorie: "rechnung", id: "r1", titel: "R-1", subtitel: null, status: "versendet", kunde_name: "Müller" },
      ],
      anzahl: { kunde: 1, auftrag: 1, rechnung: 1 },
    })),
  },
  tagsApi: { list: vi.fn(async () => []) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ currentUser: { id: "u1", role: "mandant_admin", deaktivierte_module: [] }, hatRecht: () => true }),
}));

function Ort() {
  return <output data-testid="ort">{useLocation().pathname}</output>;
}

afterEach(cleanup);

describe("Feld-SearchPage", () => {
  it("gruppiert Treffer, lässt in der Feld-App nicht erreichbare Kategorien weg und navigiert", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SearchPage />
          <Ort />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "müller" } });
    expect(await screen.findByText("Kunden · 1")).toBeInTheDocument();
    expect(screen.getByText("Rechnungen · 1")).toBeInTheDocument();
    expect(screen.queryByText("Müller Auftrag")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Aufträge/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("R-1"));
    expect(screen.getByTestId("ort")).toHaveTextContent("/rechnungen/r1");
  });
});
