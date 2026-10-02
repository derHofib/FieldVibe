// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authStore } from "../api/authStore";
import { useEventStream } from "./useEventStream";

const ticketMock = vi.fn();
vi.mock("../api/endpoints", () => ({ streamApi: { ticket: () => ticketMock() } }));

class FakeEventSource {
  static instanzen: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  geschlossen = false;
  constructor(public url: string) {
    FakeEventSource.instanzen.push(this);
  }
  addEventListener() {}
  close() {
    this.geschlossen = true;
  }
}

describe("useEventStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instanzen = [];
    ticketMock.mockReset();
    vi.stubGlobal("EventSource", FakeEventSource);
    authStore.setPrimary({ accessToken: "geheimes-access-token", refreshToken: "r" });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    authStore.clear();
  });

  it("verbindet mit Ticket statt Access-Token in der URL", async () => {
    ticketMock.mockResolvedValue({ ticket: "ticket-1", gueltig_bis: "" });
    renderHook(() => useEventStream({ x: () => {} }));
    await act(async () => {});

    expect(FakeEventSource.instanzen).toHaveLength(1);
    const url = FakeEventSource.instanzen[0].url;
    expect(url).toContain("ticket=ticket-1");
    expect(url).not.toContain("token=");
    expect(url).not.toContain("geheimes-access-token");
  });

  it("holt vor jedem Reconnect ein neues Ticket", async () => {
    ticketMock
      .mockResolvedValueOnce({ ticket: "ticket-1", gueltig_bis: "" })
      .mockResolvedValueOnce({ ticket: "ticket-2", gueltig_bis: "" });
    renderHook(() => useEventStream({ x: () => {} }));
    await act(async () => {});

    FakeEventSource.instanzen[0].onerror?.();
    expect(FakeEventSource.instanzen[0].geschlossen).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(ticketMock).toHaveBeenCalledTimes(2);
    expect(FakeEventSource.instanzen).toHaveLength(2);
    expect(FakeEventSource.instanzen[1].url).toContain("ticket=ticket-2");
  });

  it("versucht es nach fehlgeschlagener Ticket-Anfrage erneut", async () => {
    ticketMock
      .mockRejectedValueOnce(new Error("401"))
      .mockResolvedValueOnce({ ticket: "ticket-2", gueltig_bis: "" });
    renderHook(() => useEventStream({ x: () => {} }));
    await act(async () => {});
    expect(FakeEventSource.instanzen).toHaveLength(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(FakeEventSource.instanzen).toHaveLength(1);
  });

  it("schliesst die Verbindung beim Unmount", async () => {
    ticketMock.mockResolvedValue({ ticket: "ticket-1", gueltig_bis: "" });
    const { unmount } = renderHook(() => useEventStream({ x: () => {} }));
    await act(async () => {});
    unmount();
    expect(FakeEventSource.instanzen[0].geschlossen).toBe(true);
  });
});
