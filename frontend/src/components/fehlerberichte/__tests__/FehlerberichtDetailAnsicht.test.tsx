// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FehlerberichtDetail } from "../../../types";

vi.mock("../../../api/endpoints", () => ({
  fehlerberichteApi: { detail: vi.fn(), aendern: vi.fn(), liste: vi.fn(), loeschen: vi.fn(), aiBundle: vi.fn() },
}));

import { fehlerberichteApi } from "../../../api/endpoints";
import { FehlerberichtDetailAnsicht } from "../FehlerberichtDetailAnsicht";

const idee: FehlerberichtDetail = {
  id: "i1",
  art: "idee",
  mandant_id: "m1",
  mandant_name: "Elektro Muster",
  melder_name: "Max",
  titel: "Dunkler Modus im Kalender",
  schweregrad: "mittel",
  status: "neu",
  route: "/kalender",
  app_version: "1",
  commit_sha: null,
  duplikat_von_id: null,
  hat_screenshot: false,
  erledigt_am: null,
  created_at: "2026-10-04T08:00:00Z",
  updated_at: "2026-10-04T08:00:00Z",
  beschreibung: "Kalender soll dunkel sein",
  erwartet: "Weniger Blendung",
  schritte: null,
  kontext: {},
  screenshot_original_url: null,
  screenshot_annotiert_url: null,
  loesungsnotiz: null,
  fix_commit: null,
  fix_pr_url: null,
};

function rendere(ideenVerwalten: boolean) {
  vi.mocked(fehlerberichteApi.detail).mockResolvedValue(idee);
  vi.mocked(fehlerberichteApi.liste).mockResolvedValue([]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FehlerberichtDetailAnsicht
          id="i1"
          mitMandant={false}
          kannBearbeiten
          kannLoeschen={false}
          ideenVerwalten={ideenVerwalten}
          listenPfad="/fehlerberichte"
          detailPfad={(id) => `/fehlerberichte/${id}`}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("FehlerberichtDetailAnsicht bei Ideen", () => {
  it("zeigt im Office (Mandanten-Admin) Status und Lösung nur lesend", async () => {
    rendere(false);
    await waitFor(() => expect(screen.getByText("Dunkler Modus im Kalender")).toBeTruthy());
    expect(screen.getByText("Was soll sich ändern?")).toBeTruthy();
    expect(screen.getByText("Warum / Nutzen")).toBeTruthy();
    expect(screen.getByText("Priorität")).toBeTruthy();
    expect(screen.getByText("Ideen werden vom FieldVibe-Team geprüft und freigegeben.")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Status" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Freigeben" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Lösung speichern" })).toBeNull();
    expect((screen.getByLabelText("Lösungsnotiz") as HTMLTextAreaElement).disabled).toBe(true);
  });

  it("lässt den Super-Admin freigeben (Status gesichtet) und zeigt Ideen-Labels", async () => {
    vi.mocked(fehlerberichteApi.aendern).mockResolvedValue({ ...idee, status: "gesichtet" });
    rendere(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Freigeben" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "In Umsetzung" })).toBeTruthy();
    expect(screen.getByText(/Claude beim nächsten Lauf als Pull Request/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(fehlerberichteApi.aendern).toHaveBeenCalledWith("i1", { status: "gesichtet" }));
  });
});
