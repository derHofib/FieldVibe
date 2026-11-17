// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Building2 } from "lucide-react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { FilterLeiste } from "./FilterLeiste";
import type { FilterFeld } from "./typen";
import { useFilterZustand } from "./useFilterZustand";

afterEach(cleanup);

interface Zeile {
  titel: string;
  status: string;
}
const felder: FilterFeld<Zeile>[] = [
  { key: "titel", label: "Titel", typ: "text", icon: Building2, wert: (z) => z.titel },
  {
    key: "status",
    label: "Status",
    typ: "auswahl",
    icon: Building2,
    wert: (z) => z.status,
    optionen: [
      { wert: "neu", label: "Neu", status: "neu" },
      { wert: "arbeit", label: "In Arbeit", status: "arbeit" },
    ],
  },
];

function Seite() {
  const zustand = useFilterZustand({ felder });
  const { search } = useLocation();
  return (
    <>
      <FilterLeiste felder={felder} zustand={zustand} variante="office" />
      <output data-testid="url">{search}</output>
    </>
  );
}

function rendere(pfad = "/vorgaenge?seite=2") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[pfad]}>
        <Seite />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function titelFilterAnlegen(wert: string) {
  fireEvent.click(screen.getByRole("button", { name: "Filter hinzufügen" }));
  fireEvent.click(screen.getByRole("option", { name: /^Titel/ }));
  fireEvent.click(screen.getByRole("option", { name: "enthält" }));
  const eingabe = screen.getByRole("combobox", { name: "Titel enthält" });
  fireEvent.change(eingabe, { target: { value: wert } });
  fireEvent.keyDown(eingabe, { key: "Enter" });
}

describe("FilterLeiste (Office)", () => {
  it("legt eine Pille per Spalte -> Bedingung -> Wert an und behält fremde URL-Parameter", () => {
    rendere();
    titelFilterAnlegen("Wartung");
    expect(screen.getByRole("group", { name: "Filter: Titel enthält Wartung" })).toBeInTheDocument();
    expect(screen.getByTestId("url").textContent).toContain("f=");
    expect(screen.getByTestId("url").textContent).toContain("seite=2");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("mischt ein zweites 'ist' auf einer Auswahl-Spalte in die bestehende Pille", () => {
    rendere();
    const anlegen = (label: string) => {
      fireEvent.click(screen.getByRole("button", { name: "Filter hinzufügen" }));
      fireEvent.click(screen.getByRole("option", { name: /^Status/ }));
      fireEvent.click(screen.getByRole("option", { name: "ist" }));
      fireEvent.click(screen.getByRole("option", { name: label }));
      fireEvent.click(screen.getByRole("button", { name: "Fertig" }));
    };
    anlegen("Neu");
    anlegen("In Arbeit");
    expect(screen.getAllByRole("group")).toHaveLength(1);
    expect(screen.getByRole("group", { name: "Filter: Status ist Neu, In Arbeit" })).toBeInTheDocument();
  });

  it("entfernt eine Pille über das ×", () => {
    rendere();
    titelFilterAnlegen("Wartung");
    fireEvent.click(screen.getByRole("button", { name: "Filter Titel enthält Wartung entfernen" }));
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.getByTestId("url").textContent).not.toContain("f=");
  });

  it("Zurücksetzen leert Pillen und Suche", () => {
    rendere();
    titelFilterAnlegen("Wartung");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "heizung" } });
    expect(screen.getByTestId("url").textContent).toContain("q=heizung");
    fireEvent.click(screen.getByRole("button", { name: "Zurücksetzen" }));
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getByTestId("url").textContent).toBe("?seite=2");
    expect(screen.queryByRole("button", { name: "Zurücksetzen" })).toBeNull();
  });

  it("schreibt die Suche als q in die URL und liest sie beim Start", () => {
    rendere("/x");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Zähler" } });
    expect(decodeURIComponent(screen.getByTestId("url").textContent ?? "")).toContain("q=Zähler");
    cleanup();
    rendere("/x?q=abc");
    expect(screen.getByRole("searchbox")).toHaveValue("abc");
  });

  it("ignoriert Bedingungen zu unbekannten Feldern in der URL", () => {
    rendere(`/x?f=${encodeURIComponent('[["gibtsnicht","ist","x"],["titel","leer"]]')}`);
    expect(screen.getAllByRole("group")).toHaveLength(1);
    expect(screen.getByRole("group", { name: "Filter: Titel ist leer" })).toBeInTheDocument();
  });

  it("bietet 'Stattdessen suchen' an, wenn keine Spalte passt", () => {
    rendere();
    fireEvent.click(screen.getByRole("button", { name: "Filter hinzufügen" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Spalte suchen" }), { target: { value: "xyz" } });
    fireEvent.click(screen.getByRole("option", { name: "Stattdessen suchen nach ‚xyz‘" }));
    expect(screen.getByRole("searchbox")).toHaveValue("xyz");
  });
});
