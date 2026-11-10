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

  it("zeigt ohne Änderungsrecht nur den Status", () => {
    render(<VorgangStatusAktionen status="neu" darfAendern={false} pending={false} onWaehle={vi.fn()} />);
    expect(screen.getByText("Neu")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("bietet 'abgerechnet' nie als setzbaren Status an", () => {
    render(<VorgangStatusAktionen status="neu" darfAendern pending={false} onWaehle={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Status ändern" }));
    expect(screen.queryByRole("menuitem", { name: /Abgerechnet/ })).toBeNull();
    expect(screen.getByRole("menuitem", { name: /Vorgang stornieren/ })).toBeTruthy();
  });
});
