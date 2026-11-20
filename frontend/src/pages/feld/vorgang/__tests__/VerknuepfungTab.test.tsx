// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Vorgang, VorgangVerknuepfung } from "../../../../types";
import { VerknuepfungTab } from "../VerknuepfungTab";

// Der Aufgaben-Abschnitt braucht Router und QueryClient und hat eigene Tests.
vi.mock("../../aufgaben/BezugAufgabenAbschnitt", () => ({ BezugAufgabenAbschnitt: () => null }));

afterEach(cleanup);

const DATEN: VorgangVerknuepfung = {
  herkunft: [
    { art: "projekt_angelegt", text: "Projekt Heizungstausch angelegt", ref_typ: "projekt", ref_id: "p1", ref_label: "Heizungstausch", datum: "2026-11-02T08:00:00Z", person_name: "Sabine", zusatz: null, aktuell: false },
    { art: "vorgang_angelegt", text: "Vorgang V-2 im Auftrag angelegt", ref_typ: "vorgang", ref_id: "v2", ref_label: "V-2", datum: "2026-11-05T08:00:00Z", person_name: null, zusatz: null, aktuell: true },
  ],
  rueckmeldung: { arbeitszeit_sekunden: 12600, arbeitszeit_sekunden_auftrag: 45000, positionen_anzahl: 4, positionen_netto: "1240", offene_maengel: 2, status: "in_arbeit" },
  geschwister: [
    { id: "v1", vorgangsnummer: "V-1", titel: "Wartung", status: "abgeschlossen", ist_aktuell: false },
    { id: "v2", vorgangsnummer: "V-2", titel: "Fehlersuche", status: "in_arbeit", ist_aktuell: true },
  ],
  projekt: { id: "p1", name: "Heizungstausch" },
  auftrag: { id: "a1", titel: "Wärmepumpe", status: "in_arbeit" },
};

function rendern(vorgangTeil: Partial<Vorgang> = {}, onEigenstaendig = vi.fn()) {
  render(
    <VerknuepfungTab
      vorgang={{ id: "v2", ...vorgangTeil } as Vorgang}
      daten={DATEN}
      laedt={false}
      fehler={false}
      onErneut={vi.fn()}
      linksAktiv
      navigate={vi.fn()}
      vorgangPfad={(id) => `/vorgaenge/${id}`}
      onEigenstaendig={onEigenstaendig}
      eigenstaendigPending={false}
      zweispaltigMoeglich={false}
      wrapperProps={{ hidden: false }}
    />,
  );
  return onEigenstaendig;
}

describe("VerknuepfungTab", () => {
  it("zeigt Herkunft, Rückmeldung und Geschwister mit Fortschritt", () => {
    rendern();
    expect(screen.getByText("Herkunft")).toBeTruthy();
    expect(screen.getByText("Rückmeldung an den Auftrag")).toBeTruthy();
    expect(screen.getByText(/von 12,5 h im Auftrag/)).toBeTruthy();
    expect(screen.getByText(/1\.240,00\s€ netto/)).toBeTruthy();
    expect(screen.getByText("1 / 2 erledigt")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Heizungstausch" })).toBeTruthy();
  });

  it("zeigt Freigabe nur mit darf_eigenstaendig_setzen", () => {
    rendern({ darf_eigenstaendig_setzen: false });
    expect(screen.queryByText("Freigabe")).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("schaltet mit Recht um und zeigt bei 'an' seit wann und von wem", () => {
    const umschalten = rendern({
      darf_eigenstaendig_setzen: true,
      verknuepfung_eigenstaendig: true,
      verknuepfung_eigenstaendig_am: "2026-11-10T08:00:00Z",
      verknuepfung_eigenstaendig_von_name: "Ali",
    });
    expect(screen.getByText(/seit 10\.11\.2026 von Ali/)).toBeTruthy();
    const schalter = screen.getByRole("switch", { name: "Eigenständig führen" });
    expect(schalter.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(schalter);
    expect(umschalten).toHaveBeenCalledWith(false);
  });
});
