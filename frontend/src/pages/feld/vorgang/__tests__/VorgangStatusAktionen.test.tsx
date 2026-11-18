// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VorgangStatusAktionen } from "../VorgangStatusAktionen";

afterEach(cleanup);

describe("VorgangStatusAktionen", () => {
  it("bietet für in_arbeit den Schritt 'Fertig melden' an", () => {
    const onWaehle = vi.fn();
    render(<VorgangStatusAktionen status="in_arbeit" darfAendern pending={false} onWaehle={onWaehle} />);
    fireEvent.click(screen.getByRole("button", { name: /Fertig melden/ }));
    expect(onWaehle).toHaveBeenCalledWith("abgeschlossen");
  });

  it("zeigt ohne Änderungsrecht keine Buttons und keine Status-Pille (die steht im Kopf)", () => {
    render(<VorgangStatusAktionen status="neu" darfAendern={false} pending={false} onWaehle={vi.fn()} />);
    expect(screen.queryByText("Neu")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it.each([
    ["neu", "Starten"],
    ["geplant", "Starten"],
    ["in_arbeit", "Fertig melden"],
    ["wartet_kunde", "Wieder aufnehmen"],
  ] as const)("hat für %s genau die Hauptaktion '%s'", (status, label) => {
    render(<VorgangStatusAktionen status={status} darfAendern pending={false} onWaehle={vi.fn()} />);
    const primaer = screen.getAllByRole("button").filter((b) => b.className.includes("btn-ap-primary"));
    expect(primaer).toHaveLength(1);
    expect(primaer[0].textContent).toContain(label);
  });

  it("nutzt bei abgeschlossen den Ersatzschritt 'Rechnung erstellen' als Hauptaktion", () => {
    const onClick = vi.fn();
    render(
      <VorgangStatusAktionen status="abgeschlossen" darfAendern pending={false} onWaehle={vi.fn()} ersatzSchritt={{ label: "Rechnung erstellen", onClick }} />,
    );
    const knopf = screen.getByRole("button", { name: "Rechnung erstellen" });
    expect(knopf.className).toContain("btn-ap-primary");
    fireEvent.click(knopf);
    expect(onClick).toHaveBeenCalled();
  });

  it("macht den Schritt sekundär, wenn die Seite schon eine Primäraktion zeigt", () => {
    const { rerender } = render(<VorgangStatusAktionen status="neu" darfAendern pending={false} onWaehle={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Starten/ }).className).toContain("btn-ap-primary");
    rerender(<VorgangStatusAktionen status="neu" darfAendern pending={false} onWaehle={vi.fn()} primaer={false} />);
    expect(screen.getByRole("button", { name: /Starten/ }).className).not.toContain("btn-ap-primary");
  });

  it("bietet 'abgerechnet' nie als setzbaren Status an", () => {
    render(<VorgangStatusAktionen status="neu" darfAendern pending={false} onWaehle={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Status ändern/ }));
    expect(screen.queryByRole("menuitem", { name: /Abgerechnet/ })).toBeNull();
    expect(screen.getByRole("menuitem", { name: /Vorgang stornieren/ })).toBeTruthy();
  });
});
