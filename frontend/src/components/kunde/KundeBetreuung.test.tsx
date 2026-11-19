// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { kundenApi, usersApi } from "../../api/endpoints";
import type { Betreuer, UserAuswahl } from "../../types";
import { KundeBetreuung } from "./KundeBetreuung";

vi.mock("../../api/endpoints", () => ({
  kundenApi: { betreuungSetzen: vi.fn() },
  usersApi: { auswahl: vi.fn() },
}));

const betreuer = (user_id: string, name: string, extra: Partial<Betreuer> = {}): Betreuer => ({
  user_id,
  name,
  avatar_url: null,
  hauptbetreuer: false,
  aktiv: true,
  nur_betreute_kunden: false,
  account_typ_name: null,
  ...extra,
});
const mitarbeiter = (id: string, name: string, extra: Partial<UserAuswahl> = {}) =>
  ({ id, name, role: "custom", aktiv: true, nur_zugewiesene_kunden: false, account_typ_name: null, avatar_url: null, account_typ_id: null, ...extra }) as UserAuswahl;

function rendern(bisher: Betreuer[], kannVerwalten = true) {
  vi.mocked(usersApi.auswahl).mockResolvedValue([
    mitarbeiter("u1", "Jonas Weber", { nur_zugewiesene_kunden: true }),
    mitarbeiter("u2", "Lena Schulz"),
    mitarbeiter("u3", "Murat Aydin"),
  ]);
  vi.mocked(kundenApi.betreuungSetzen).mockResolvedValue([]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KundeBetreuung kundeId="k1" betreuung={bisher} kannVerwalten={kannVerwalten} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KundeBetreuung", () => {
  it("leer: Hinweistext, ohne Recht keine Ändern-Zeile", () => {
    rendern([], false);
    expect(screen.getByText("Noch niemand betreut diesen Kunden.")).toBeInTheDocument();
    expect(screen.queryByText("Betreuung ändern")).not.toBeInTheDocument();
  });

  it("zeigt Hauptbetreuer/Vertretung, deaktivierte und den Vorbelegungs-Hinweis", () => {
    rendern([betreuer("u1", "Jonas Weber", { hauptbetreuer: true }), betreuer("u9", "Alt Nutzer", { aktiv: false })]);
    expect(screen.getByText("Hauptbetreuer")).toBeInTheDocument();
    expect(screen.getByText(/Vertretung · deaktiviert/)).toBeInTheDocument();
    expect(screen.getByText("Neue Vorgänge für diesen Kunden werden automatisch Jonas Weber zugewiesen.")).toBeInTheDocument();
  });

  it("Sheet: Stern setzen, Warnung bei Abwahl, Speichern sendet user_ids und hauptbetreuer_id", async () => {
    rendern([betreuer("u1", "Jonas Weber", { hauptbetreuer: true, nur_betreute_kunden: true }), betreuer("u2", "Lena Schulz")]);
    fireEvent.click(screen.getByText("Betreuung ändern"));
    await screen.findByRole("checkbox", { name: /Murat Aydin/ });

    // Stern bei Murat: setzt Häkchen mit und nimmt ihn Jonas weg
    const sterne = screen.getAllByRole("button", { name: "Als Hauptbetreuer festlegen" });
    fireEvent.click(sterne[2]);
    expect(screen.getByRole("checkbox", { name: /Murat Aydin/ })).toHaveAttribute("aria-checked", "true");
    expect(sterne[2]).toHaveAttribute("aria-pressed", "true");
    expect(sterne[0]).toHaveAttribute("aria-pressed", "false");

    // Jonas (sieht nur betreute Kunden) abwählen -> Warnung
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /Jonas Weber/ }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Jonas Weber sieht nur betreute Kunden und sieht diesen Kunden und seine Vorgänge danach nicht mehr.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Fertig" }));
    await waitFor(() =>
      expect(kundenApi.betreuungSetzen).toHaveBeenCalledWith("k1", { user_ids: ["u2", "u3"], hauptbetreuer_id: "u3" }),
    );
  });

  it("erneutes Tippen auf den Stern nimmt ihn weg", async () => {
    rendern([betreuer("u1", "Jonas Weber", { hauptbetreuer: true })]);
    fireEvent.click(screen.getByText("Betreuung ändern"));
    await screen.findByRole("checkbox", { name: /Jonas Weber/ });
    fireEvent.click(screen.getAllByRole("button", { name: "Als Hauptbetreuer festlegen" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Fertig" }));
    await waitFor(() =>
      expect(kundenApi.betreuungSetzen).toHaveBeenCalledWith("k1", { user_ids: ["u1"], hauptbetreuer_id: null }),
    );
  });
});
