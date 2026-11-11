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
});
