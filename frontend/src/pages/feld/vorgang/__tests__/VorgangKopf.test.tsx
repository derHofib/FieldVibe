// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { heuteIso } from "../../../../utils/format";
import { VorgangKopf } from "../VorgangKopf";

afterEach(cleanup);

type Props = ComponentProps<typeof VorgangKopf>;

function rendern(vorgangTeil: Record<string, unknown> = {}, propsTeil: Partial<Props> = {}) {
  const props = {
    vorgang: {
      id: "v1",
      vorgangsnummer: "V-1",
      titel: "Wartung",
      status: "neu",
      prioritaet: 2,
      kunde_id: "k1",
      zugewiesener_user_id: null,
      zugewiesener_name: null,
      dauerauftrag_id: null,
      faelligkeit_am: null,
      ...vorgangTeil,
    },
    kunde: { id: "k1", name: "Herdrich" },
    anlage: undefined,
    standort: undefined,
    anzeigeAdresse: null,
    layout: "dicht",
    primaerAktionKlebt: false,
    kannDisponieren: true,
    kannLoeschen: true,
    currentUser: { id: "u1", darf_vorgaenge_selbst_uebernehmen: true },
    users: undefined,
    naechsterTermin: undefined,
    navigate: vi.fn(),
    onZurueck: vi.fn(),
    onGanzeSeite: vi.fn(),
    onLinkKopieren: vi.fn(),
    onPrioritaet: vi.fn(),
    onZuweisen: vi.fn(),
    onUebernehmen: vi.fn(),
    uebernehmenPending: false,
    onFaelligkeit: vi.fn(),
    onTerminOeffnen: vi.fn(),
    statusPending: false,
    onStatusWaehle: vi.fn(),
    rechnung: null,
    onZeitErfassen: vi.fn(),
    onFolgeVorgang: vi.fn(),
    onZuordnungAendern: vi.fn(),
    onLoeschen: vi.fn(),
    loeschenPending: false,
    ...propsTeil,
  } as unknown as Props;
  render(<VorgangKopf {...props} />);
  return props;
}

describe("VorgangKopf", () => {
  it("ändert die Priorität über das Chip-Menü", () => {
    const props = rendern();
    const chip = screen.getByRole("button", { name: /Priorität 2/ });
    expect(chip.getAttribute("aria-haspopup")).toBe("menu");
    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Priorität 4/ }));
    expect(props.onPrioritaet).toHaveBeenCalledWith(4);
  });

  it("zeigt nach einer (fehlgeschlagenen) Änderung weiter den gespeicherten Wert", () => {
    // Die Mutation ändert das Vorgang-Objekt nicht -- bei Fehler bleibt der Chip am gespeicherten Wert
    // (früher zeigte das native Select den zuletzt gewählten Wert weiter an).
    rendern();
    fireEvent.click(screen.getByRole("button", { name: /Priorität 2/ }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Priorität 5/ }));
    expect(screen.getByRole("button", { name: /Priorität 2/ })).toBeTruthy();
    expect(screen.queryByText(/Priorität 5/)).toBeNull();
  });

  it("zeigt die Priorität bei Dauerauftrag nur an", () => {
    rendern({ dauerauftrag_id: "d1" });
    expect(screen.queryByRole("button", { name: /Priorität/ })).toBeNull();
    expect(screen.getByText(/Priorität 2 · automatisch/).getAttribute("title")).toMatch(/automatisch/);
  });

  it("sperrt die Priorität bei geschlossenem Vorgang", () => {
    rendern({ status: "abgeschlossen" });
    expect(screen.queryByRole("button", { name: /Priorität/ })).toBeNull();
    expect(screen.getByText("Priorität 2")).toBeTruthy();
  });

  it("zeigt Status, Priorität und Zuständigkeit jeweils genau einmal", () => {
    rendern({ status: "in_arbeit", zugewiesener_user_id: "u2", zugewiesener_name: "Dennis Hofmann" });
    expect(screen.getAllByText("In Arbeit")).toHaveLength(1);
    expect(screen.getAllByText(/Priorität 2/)).toHaveLength(1);
    expect(screen.getAllByText("Dennis Hofmann")).toHaveLength(1);
    expect(screen.queryByText(/Nicht zugewiesen/)).toBeNull();
  });

  it("weist per Chip mir zu und entfernt die Zuweisung nur mit Personenauswahl", () => {
    const props = rendern(
      { zugewiesener_user_id: "u2", zugewiesener_name: "Dennis" },
      { users: [{ id: "u2", name: "Dennis", aktiv: true }, { id: "u3", name: "Sabine", aktiv: true }] as Props["users"] },
    );
    fireEvent.click(screen.getByRole("button", { name: /Dennis/ }));
    fireEvent.click(screen.getByRole("button", { name: "Sabine" }));
    expect(props.onZuweisen).toHaveBeenCalledWith("u3");
  });

  it("bietet ohne Nutzerliste nur 'Mir zuweisen' an", () => {
    const props = rendern();
    fireEvent.click(screen.getByRole("button", { name: /Nicht zugewiesen/ }));
    expect(screen.queryByLabelText("Person suchen")).toBeNull();
    expect(screen.queryByText("Zuweisung entfernen")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Mir zuweisen/ }));
    expect(props.onUebernehmen).toHaveBeenCalled();
  });

  it("markiert überfällige Fälligkeit rot mit Tagen", () => {
    rendern({ status: "in_arbeit", faelligkeit_am: `${heuteIso(-3)}T12:00:00` });
    const chip = screen.getByRole("button", { name: /Tage überfällig/ });
    expect(chip.className).toContain("bg-st-fehlt-bg");
  });

  it("zeigt leere Fälligkeit gedämpft im Office, in der Feld-App gar nicht", () => {
    rendern();
    expect(screen.getByText("Keine Fälligkeit")).toBeTruthy();
    cleanup();
    rendern({}, { layout: "kompakt" });
    expect(screen.queryByText("Keine Fälligkeit")).toBeNull();
  });

  it("setzt die Fälligkeit über die Datumsauswahl", () => {
    const props = rendern();
    fireEvent.click(screen.getByRole("button", { name: /Keine Fälligkeit/ }));
    fireEvent.change(screen.getByLabelText("Fälligkeitsdatum"), { target: { value: "2026-12-01" } });
    expect(props.onFaelligkeit).toHaveBeenCalledWith("2026-12-01");
  });

  it("zeigt den Termin-Chip nur mit Termin und wechselt per Klick", () => {
    rendern();
    expect(screen.queryByRole("button", { name: /Termin/ })).toBeNull();
    cleanup();
    const props = rendern({}, { naechsterTermin: { start_at: "2026-11-20T08:00:00Z" } });
    fireEvent.click(screen.getByRole("button", { name: /Termin/ }));
    expect(props.onTerminOeffnen).toHaveBeenCalled();
  });

  it("zeigt je Status genau eine Hauptaktion plus Zusatz", () => {
    rendern({ status: "in_arbeit" });
    const primaer = screen.getAllByRole("button").filter((b) => b.className.includes("btn-ap-primary"));
    expect(primaer.map((b) => b.textContent)).toEqual([expect.stringContaining("Fertig melden")]);
    expect(screen.getByRole("button", { name: /Zeit erfassen/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Status ändern/ })).toBeTruthy();
  });

  it("bietet bei abgeschlossen 'Rechnung erstellen' als Hauptaktion", () => {
    const onClick = vi.fn();
    rendern({ status: "abgeschlossen" }, { rechnung: { onClick, pending: false } });
    fireEvent.click(screen.getByRole("button", { name: "Rechnung erstellen" }));
    expect(onClick).toHaveBeenCalled();
  });

  it("macht die Leiste sekundär und blendet Zusatzaktionen aus, wenn die klebende Leiste führt", () => {
    rendern({ status: "neu" }, { layout: "kompakt", primaerAktionKlebt: true });
    expect(screen.getByRole("button", { name: /Starten/ }).className).not.toContain("btn-ap-primary");
    expect(screen.queryByRole("button", { name: /^Übernehmen/ })).toBeNull();
  });

  it("zeigt 'Übernehmen' bei Neu nur, wenn nicht mir zugewiesen", () => {
    rendern({ status: "neu" });
    expect(screen.getByRole("button", { name: /^Übernehmen/ })).toBeTruthy();
    cleanup();
    rendern({ status: "neu", zugewiesener_user_id: "u1", zugewiesener_name: "Ich" });
    expect(screen.queryByRole("button", { name: /^Übernehmen/ })).toBeNull();
  });

  it("verkürzt die Chips in der Feld-App ('Prio 2', 'Ich')", () => {
    rendern({ zugewiesener_user_id: "u1", zugewiesener_name: "Dennis" }, { layout: "kompakt" });
    expect(screen.getByText("Prio 2")).toBeTruthy();
    expect(screen.getByText("Ich")).toBeTruthy();
  });

  it("hat Icon-Buttons 'Ganze Seite' und das Menü mit Löschen nur mit Recht", () => {
    const props = rendern();
    fireEvent.click(screen.getByRole("button", { name: "Ganze Seite" }));
    expect(props.onGanzeSeite).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Weitere Aktionen" }));
    expect(screen.getByRole("menuitem", { name: /Vorgang löschen/ })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /Link kopieren/ })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /Kunde \/ Anlage ändern/ })).toBeTruthy();
  });

  it("blendet 'Vorgang löschen' ohne Recht aus", () => {
    rendern({}, { kannLoeschen: false });
    fireEvent.click(screen.getByRole("button", { name: "Weitere Aktionen" }));
    expect(screen.queryByRole("menuitem", { name: /Vorgang löschen/ })).toBeNull();
  });
});
