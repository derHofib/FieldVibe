// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({
  kundenApi: {
    verwaltete: vi.fn(async () => [{ id: "weg", name: "WEG Moselstraße 14" }]),
    list: vi.fn(async () => [
      { id: "hv", name: "Hausverwaltung Rheinblick" },
      { id: "weg", name: "WEG Moselstraße 14" },
      { id: "x", name: "Müller GmbH" },
    ]),
  },
}));

import { RechnungAnAbschnitt } from "./RechnungAnAbschnitt";

afterEach(cleanup);

function rendern(props: Partial<Parameters<typeof RechnungAnAbschnitt>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RechnungAnAbschnitt
        auftraggeberId="hv"
        auftraggeberName="Hausverwaltung Rheinblick"
        rechnungAn={null}
        speichern={vi.fn()}
        laeuft={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("RechnungAnAbschnitt", () => {
  it("zeigt ohne Empfänger den Auftraggeber als Standard", () => {
    rendern();
    expect(screen.getByText("Rechnung an")).toBeInTheDocument();
    expect(screen.getByText("Auftraggeber")).toBeInTheDocument();
  });

  it("bietet zuerst die verwalteten Kunden an und speichert die Wahl", async () => {
    const speichern = vi.fn();
    rendern({ speichern });
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    fireEvent.focus(screen.getByRole("textbox"));
    const weg = await screen.findByText("Verwaltet von Hausverwaltung Rheinblick");
    fireEvent.click(weg);
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(speichern).toHaveBeenCalled());
    expect(speichern.mock.calls[0][0]).toBe("weg");
  });

  it("zeigt bei verwaltetem Empfänger grau c/o den Verwalter", () => {
    rendern({ rechnungAn: { id: "weg", name: "WEG Moselstraße 14", verwaltet_von_name: "Hausverwaltung Rheinblick" } });
    expect(screen.getByText(/WEG Moselstraße 14/)).toBeInTheDocument();
    expect(screen.getByText("c/o Hausverwaltung Rheinblick")).toBeInTheDocument();
  });

  it("rendert nichts ohne Auftraggeber", () => {
    const { container } = rendern({ auftraggeberId: null, auftraggeberName: null });
    expect(container).toBeEmptyDOMElement();
  });
});
