// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PositionDetail, Position, RechteRegistry } from "../../types/organigramm";

vi.mock("../../api/endpoints", () => ({
  organigrammApi: { setPositionRechte: vi.fn(() => Promise.resolve([])) },
}));

import { organigrammApi } from "../../api/endpoints";
import { listenZeilen } from "./liste";
import { OrganigrammListe } from "./OrganigrammListe";
import { PositionKontextMenue } from "./PositionKontextMenue";
import { RechteTab } from "./RechteTab";

afterEach(cleanup);

const REGISTRY: RechteRegistry = {
  scopes: ["eigene", "team", "teilbaum", "bereich", "mandant"],
  bereiche: [
    { key: "vorgaenge", label: "Aufträge", aktionen: ["sehen", "loeschen"], scopes: ["eigene", "team", "teilbaum", "bereich", "mandant"], modul: null },
    { key: "material", label: "Material", aktionen: ["sehen", "loeschen"], scopes: ["mandant"], modul: null },
  ],
};

const DETAIL: PositionDetail = {
  id: "p1",
  parent_id: "w",
  titel: "Teamleitung",
  typ: "linie",
  status: "besetzt",
  soll_besetzung: 1,
  ist_besetzung: 1,
  besetzungen: [],
  alle_besetzungen: [],
  account_typ: { id: "t1", name: "Teamleiter" },
  overrides: [],
  effektive_rechte: [{ bereich: "vorgaenge", aktion: "sehen", scope: "team", herkunft: [{ art: "account_typ", account_typ_id: "t1" }] }],
  diff_zur_vorlage: [],
  unterpositionen: 0,
};

function rendereRechteTab(darfVerwalten: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RechteTab detail={DETAIL} registry={REGISTRY} accountTypen={[]} darfRechteVerwalten={darfVerwalten} onGespeichert={() => {}} />
    </QueryClientProvider>,
  );
}

describe("RechteTab", () => {
  it("bietet je Zelle nur Scopes aus der Registry an und zeigt die Vorlage", () => {
    rendereRechteTab(true);
    const vorgaengeSehen = screen.getByRole("combobox", { name: /Aufträge – Sehen: Aus Vorlage, Team/ });
    expect(within(vorgaengeSehen).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Vorlage: Team",
      "Erlaubt: Eigene",
      "Erlaubt: Team",
      "Erlaubt: Teilbaum",
      "Erlaubt: Bereich",
      "Erlaubt: Mandant",
      "Verweigert",
    ]);
    const materialSehen = screen.getByRole("combobox", { name: /Material – Sehen/ });
    expect(within(materialSehen).getAllByRole("option").map((o) => o.textContent)).toEqual(["Vorlage: –", "Erlaubt: Mandant", "Verweigert"]);
  });

  it("speichert Overrides als PUT-Payload und laesst Vorlage-Zellen weg", async () => {
    rendereRechteTab(true);
    fireEvent.change(screen.getByRole("combobox", { name: /Material – Sehen/ }), { target: { value: "erlauben:mandant" } });
    fireEvent.change(screen.getByRole("combobox", { name: /Aufträge – Löschen/ }), { target: { value: "verweigern" } });
    fireEvent.click(screen.getByRole("button", { name: "Rechte speichern" }));
    await waitFor(() => expect(organigrammApi.setPositionRechte).toHaveBeenCalled());
    expect(organigrammApi.setPositionRechte).toHaveBeenCalledWith("p1", [
      { bereich: "vorgaenge", aktion: "loeschen", wirkung: "verweigern" },
      { bereich: "material", aktion: "sehen", wirkung: "erlauben", scope: "mandant" },
    ]);
  });

  it("ist ohne rechte_verwalten schreibgeschuetzt", () => {
    rendereRechteTab(false);
    expect((screen.getByRole("combobox", { name: /Material – Sehen/ }) as HTMLSelectElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Rechte speichern" })).toBeNull();
  });
});

describe("PositionKontextMenue", () => {
  it("rendert genau die uebergebenen Aktionen", () => {
    render(<PositionKontextMenue anker={{ x: 10, y: 10 }} aktionen={["details", "darunter", "loeschen"]} onWahl={() => {}} onClose={() => {}} />);
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Details öffnen", "Position darunter anlegen", "Löschen"]);
  });

  it("meldet die gewaehlte Aktion", () => {
    const onWahl = vi.fn();
    render(<PositionKontextMenue anker={{ x: 0, y: 0 }} aktionen={["details", "platzhalter"]} onWahl={onWahl} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("menuitem", { name: "Platzhalter anlegen" }));
    expect(onWahl).toHaveBeenCalledWith("platzhalter");
  });
});

describe("OrganigrammListe", () => {
  const POSITIONEN: Position[] = [
    { id: "w", parent_id: null, titel: "Geschäftsführung", typ: "linie", status: "besetzt", soll_besetzung: 1, ist_besetzung: 1, besetzungen: [{ id: "b", user_id: "u", name: "Max Muster", art: "regulaer", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null }] },
    { id: "t", parent_id: "w", titel: "Technik", typ: "linie", status: "vakant", soll_besetzung: 2, ist_besetzung: 0, besetzungen: [] },
  ];

  it("ist eine echte Tabelle mit sortierbaren Spaltenkoepfen", () => {
    const onSortieren = vi.fn();
    render(
      <OrganigrammListe
        zeilen={listenZeilen(POSITIONEN)}
        sortierung="baum"
        richtung="auf"
        onSortieren={onSortieren}
        onWaehlen={() => {}}
        onMenue={() => {}}
        ausgewaehltId={null}
      />,
    );
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: /Position/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(screen.getByRole("rowheader", { name: "Technik" })).toBeTruthy();
    expect(screen.getByText("Max Muster")).toBeTruthy();
    expect(screen.getByText("0/2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Status/ }));
    expect(onSortieren).toHaveBeenCalledWith("status");
  });
});
