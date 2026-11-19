// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "../Toast";

function Ausloeser() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.erfolg("Gespeichert")}>ok</button>
      <button onClick={() => toast.fehler("Kaputt")}>err</button>
    </>
  );
}

describe("Toast", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("zeigt Erfolg als status und Fehler als alert", () => {
    render(
      <ToastProvider>
        <Ausloeser />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("ok"));
    fireEvent.click(screen.getByText("err"));
    expect(screen.getByRole("status").textContent).toContain("Gespeichert");
    expect(screen.getByRole("alert").textContent).toContain("Kaputt");
  });

  it("blendet sich automatisch aus", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Ausloeser />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("ok"));
    act(() => {
      vi.advanceTimersByTime(4500);
    });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("Toast mit Aktion: Button löst aus, schließt den Toast und bleibt 6 s", () => {
    vi.useFakeTimers();
    const rueckgaengig = vi.fn();
    function Mit() {
      const toast = useToast();
      return <button onClick={() => toast.erfolg("Erledigt", { label: "Rückgängig", onClick: rueckgaengig })}>an</button>;
    }
    render(
      <ToastProvider>
        <Mit />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("an"));
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByRole("status")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rückgängig" }));
    expect(rueckgaengig).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.click(screen.getByText("an"));
    act(() => vi.advanceTimersByTime(6100));
    expect(screen.queryByRole("status")).toBeNull();
  });
});
