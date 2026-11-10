// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { mutationToasts, ToastProvider } from "../Toast";

describe("mutationToasts", () => {
  afterEach(cleanup);

  it("zeigt Erfolg nur mit meta.erfolg", () => {
    render(<ToastProvider>{null}</ToastProvider>);
    act(() => {
      mutationToasts.erfolg({});
    });
    expect(screen.queryByRole("status")).toBeNull();
    act(() => {
      mutationToasts.erfolg({ erfolg: "Gespeichert" });
    });
    expect(screen.getByRole("status").textContent).toContain("Gespeichert");
  });

  it("zeigt Fehler nur ohne eigenes onError", () => {
    render(<ToastProvider>{null}</ToastProvider>);
    act(() => {
      mutationToasts.fehler(new Error("x"), true, undefined);
    });
    expect(screen.queryByRole("alert")).toBeNull();
    act(() => {
      mutationToasts.fehler(new Error("x"), false, undefined);
    });
    expect(screen.getByRole("alert").textContent).toContain("fehlgeschlagen");
  });
});
