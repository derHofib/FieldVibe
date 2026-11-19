// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { kundenApi } from "../../api/endpoints";
import { ToastProvider } from "../../components/Toast";
import type { Kunde, UserAuswahl } from "../../types";
import { KundenSammelleiste } from "./KundenSammelleiste";

vi.mock("../../api/endpoints", () => ({ kundenApi: { betreuungSammel: vi.fn() } }));

const kunde = (id: string, betreuung: Kunde["betreuung"] = []) => ({ id, name: `Kunde ${id}`, betreuung }) as Kunde;
const mitarbeiter = (id: string, name: string, nur = false) =>
  ({ id, name, role: "custom", aktiv: true, nur_zugewiesene_kunden: nur, account_typ_name: "Techniker" }) as UserAuswahl;

const alle = [
  kunde("1", [{ user_id: "u1", name: "Jonas Weber", hauptbetreuer: true }]),
  kunde("2"),
  kunde("3", [{ user_id: "u1", name: "Jonas Weber", hauptbetreuer: true }]),
];
const personen = [mitarbeiter("u1", "Jonas Weber", true), mitarbeiter("u2", "Lena Schulz")];

function rendern(onLeeren = vi.fn()) {
  vi.mocked(kundenApi.betreuungSammel).mockResolvedValue({ geaendert: 2 });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <KundenSammelleiste ausgewaehlt={[alle[0], alle[1]]} alle={alle} mitarbeiter={personen} onLeeren={onLeeren} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return onLeeren;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KundenSammelleiste", () => {
  it("nennt die Anzahl und bietet die drei Aktionen und Aufheben", () => {
    rendern();
    expect(screen.getByText("2 Kunden ausgewählt")).toBeInTheDocument();
    for (const n of ["Betreuer hinzufügen", "Hauptbetreuer setzen", "Betreuer entfernen", "Auswahl aufheben"]) {
      expect(screen.getByRole("button", { name: new RegExp(n) })).toBeInTheDocument();
    }
  });

  it("hinzufügen: Person wählen ruft die Sammel-API mit auch_hauptbetreuer (Standard an) und leert die Auswahl", async () => {
    const onLeeren = rendern();
    fireEvent.click(screen.getByRole("button", { name: /Betreuer hinzufügen/ }));
    fireEvent.click(screen.getByRole("button", { name: /Lena Schulz/ }));
    await waitFor(() =>
      expect(kundenApi.betreuungSammel).toHaveBeenCalledWith({
        kunde_ids: ["1", "2"],
        aktion: "hinzufuegen",
        user_id: "u2",
        auch_hauptbetreuer: true,
      }),
    );
    await waitFor(() => expect(onLeeren).toHaveBeenCalled());
  });

  it("hinzufügen: abgewählte Option sendet auch_hauptbetreuer false", async () => {
    rendern();
    fireEvent.click(screen.getByRole("button", { name: /Betreuer hinzufügen/ }));
    fireEvent.click(screen.getByLabelText(/Gleich als Hauptbetreuer setzen/));
    fireEvent.click(screen.getByRole("button", { name: /Lena Schulz/ }));
    await waitFor(() =>
      expect(kundenApi.betreuungSammel).toHaveBeenCalledWith(expect.objectContaining({ auch_hauptbetreuer: false })),
    );
  });

  it("entfernen: nur bisherige Betreuer, Warnung bei Sichtverlust, Aktion entfernen", async () => {
    rendern();
    fireEvent.click(screen.getByRole("button", { name: /Betreuer entfernen/ }));
    expect(screen.queryByRole("button", { name: /Lena Schulz/ })).not.toBeInTheDocument();
    const jonas = screen.getByRole("button", { name: /Jonas Weber/ });
    fireEvent.mouseEnter(jonas);
    expect(screen.getByRole("alert")).toHaveTextContent("Jonas Weber sieht nur betreute Kunden");
    expect(screen.getByText("Entfernt Jonas Weber bei 1 von 2 Kunden.")).toBeInTheDocument();
    fireEvent.click(jonas);
    await waitFor(() =>
      expect(kundenApi.betreuungSammel).toHaveBeenCalledWith({ kunde_ids: ["1", "2"], aktion: "entfernen", user_id: "u1" }),
    );
  });

  it("Hauptbetreuer setzen sendet Aktion hauptbetreuer ohne auch_hauptbetreuer; Esc schließt das Menü", async () => {
    rendern();
    fireEvent.click(screen.getByRole("button", { name: /Hauptbetreuer setzen/ }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Hauptbetreuer setzen/ }));
    fireEvent.click(screen.getByRole("button", { name: /Jonas Weber/ }));
    await waitFor(() =>
      expect(kundenApi.betreuungSammel).toHaveBeenCalledWith({ kunde_ids: ["1", "2"], aktion: "hauptbetreuer", user_id: "u1" }),
    );
  });
});
