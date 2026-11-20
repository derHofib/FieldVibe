// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SearchHit, SearchResponse } from "../../types";
import { GlobaleSucheProvider, useGlobaleSucheFenster } from "./GlobaleSucheProvider";

const hilfe = vi.hoisted(() => ({ suchen: vi.fn() }));

vi.mock("../../api/endpoints", () => ({
  searchApi: { search: hilfe.suchen },
  tagsApi: { list: vi.fn(async () => [{ id: "t1", label: "ems" }]) },
}));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: { id: "u1", role: "mandant_admin", deaktivierte_module: [] },
    hatRecht: () => true,
  }),
}));

const treffer: SearchHit[] = [
  { kategorie: "kunde", id: "k1", titel: "Müller Haustechnik", subtitel: null, nummer: "K-1" },
  { kategorie: "kunde", id: "k2", titel: "Müller Logistik", subtitel: null, nummer: "K-2" },
  { kategorie: "vorgang", id: "v1", titel: "V-1: Heizung", subtitel: null, nummer: "V-1", status: "in_arbeit" },
];
const antwort: SearchResponse = { treffer, anzahl: { kunde: 2, vorgang: 1 } };

function Ort() {
  const { pathname, search } = useLocation();
  return <output data-testid="ort">{pathname + search}</output>;
}
function Oeffner() {
  const { oeffnen } = useGlobaleSucheFenster();
  return <button onClick={() => oeffnen()}>Suche öffnen</button>;
}

function rendere() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/start"]}>
        <GlobaleSucheProvider>
          <Oeffner />
          <Ort />
        </GlobaleSucheProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText("Suche öffnen"));
  return screen.getByRole("combobox");
}

beforeEach(() => {
  localStorage.clear();
  hilfe.suchen.mockReset();
  hilfe.suchen.mockResolvedValue(antwort);
});
afterEach(cleanup);

describe("GlobaleSuche", () => {
  it("öffnet als Dialog mit Fokus im Suchfeld und schließt per Esc", () => {
    const eingabe = rendere();
    expect(screen.getByRole("dialog", { name: "Globale Suche" })).toHaveAttribute("aria-modal", "true");
    expect(eingabe).toHaveFocus();
    fireEvent.keyDown(eingabe, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("↓↓ Enter öffnet die gewählte Zeile (Kunden mit Titelpräfix-Treffer vor Vorgängen)", async () => {
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "müller" } });
    await screen.findAllByRole("option");
    // "müller" ist Titelpräfix der Kunden, deren Gruppe steht daher vor dem Vorgang
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(eingabe, { key: "ArrowDown" });
    fireEvent.keyDown(eingabe, { key: "ArrowDown" });
    expect(eingabe).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[2].id);
    fireEvent.keyDown(eingabe, { key: "Enter" });
    expect(screen.getByTestId("ort")).toHaveTextContent("/vorgaenge/v1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Strg+Enter öffnet in neuem Tab und lässt das Fenster offen", async () => {
    const offen = vi.spyOn(window, "open").mockReturnValue(null);
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "müller" } });
    await screen.findAllByRole("option");
    fireEvent.keyDown(eingabe, { key: "Enter", ctrlKey: true });
    expect(offen).toHaveBeenCalledWith("/kunden/k1", "_blank", "noopener");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    offen.mockRestore();
  });

  it("Tab wechselt die Kategorie und fragt sie einzeln ab", async () => {
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "müller" } });
    await screen.findAllByRole("option");
    fireEvent.keyDown(eingabe, { key: "Tab" });
    // Pillen nach Trefferzahl: Alle, Kunden (2), Vorgänge (1)
    await waitFor(() => expect(screen.getByRole("button", { name: /^Kunden/ })).toHaveAttribute("aria-pressed", "true"));
    await waitFor(() =>
      expect(hilfe.suchen).toHaveBeenCalledWith("müller", expect.objectContaining({ kategorie: "kunde", limit: 25 })),
    );
    fireEvent.keyDown(eingabe, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: /^Alle/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("zeigt Gruppenköpfe mit Zahl, Seiten-Treffer und merkt geöffnete Datensätze", async () => {
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "müller" } });
    await screen.findAllByRole("option");
    expect(screen.getByText("Kunden · 2")).toBeInTheDocument();
    expect(screen.getByText("Vorgänge · 1")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("option")[1]);
    const gemerkt = JSON.parse(localStorage.getItem("suche.zuletzt.u1") ?? "[]");
    expect(gemerkt[0]).toMatchObject({ kategorie: "kunde", id: "k2" });
  });

  it("Leerzustand: Zuletzt geöffnet und Tags, Klick auf Tag setzt #tag", async () => {
    localStorage.setItem(
      "suche.zuletzt.u1",
      JSON.stringify([{ kategorie: "kunde", id: "k9", titel: "Familie Hartmann", untertitel: "K-9" }]),
    );
    const eingabe = rendere();
    expect(screen.getByText("Zuletzt geöffnet")).toBeInTheDocument();
    expect(screen.getByText("Familie Hartmann")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "#ems" }));
    expect(eingabe).toHaveValue("#ems");
  });

  it("filtert „Springen zu“ clientseitig und zeigt passende Seiten als eigene Gruppe", async () => {
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "rechn" } });
    expect(await screen.findByText("Seiten")).toBeInTheDocument();
    fireEvent.keyDown(eingabe, { key: "Enter" });
    expect(screen.getByTestId("ort")).toHaveTextContent("/rechnungen");
  });

  it("keine Treffer: eigener Leerzustand mit Suchbegriff", async () => {
    hilfe.suchen.mockResolvedValue({ treffer: [], anzahl: {} });
    const eingabe = rendere();
    fireEvent.change(eingabe, { target: { value: "zzz" } });
    expect(await screen.findByText("Keine Treffer für „zzz“")).toBeInTheDocument();
  });

  it("gibt den Fokus beim Schließen zurück", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <GlobaleSucheProvider>
            <Oeffner />
          </GlobaleSucheProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const knopf = screen.getByText("Suche öffnen");
    knopf.focus();
    fireEvent.click(knopf);
    expect(screen.getByRole("combobox")).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(knopf).toHaveFocus();
  });
});
