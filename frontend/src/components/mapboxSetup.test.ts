import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mapboxStub = vi.hoisted(() => ({ accessToken: "" }));
vi.mock("mapbox-gl", () => ({ default: mapboxStub }));

const urspruenglichesFetch = globalThis.fetch;
let originalFetch: ReturnType<typeof vi.fn>;

// Modul-Flag (sperreAktiv) pro Test zuruecksetzen, sonst sieht der zweite
// Test das bereits gewickelte fetch des ersten.
async function ladeHelfer() {
  vi.resetModules();
  return import("./mapboxSetup");
}

beforeEach(() => {
  originalFetch = vi.fn().mockResolvedValue(new Response("ok", { status: 200 }));
  globalThis.fetch = originalFetch as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = urspruenglichesFetch;
});

describe("istMapboxEventsRequest", () => {
  it("erkennt den Events-Host als String, URL und Request", async () => {
    const { istMapboxEventsRequest } = await ladeHelfer();
    const url = "https://events.mapbox.com/events/v2?access_token=pk.x";
    expect(istMapboxEventsRequest(url)).toBe(true);
    expect(istMapboxEventsRequest(new URL(url))).toBe(true);
    expect(istMapboxEventsRequest(new Request(url, { method: "POST", body: "[]" }))).toBe(true);
    expect(istMapboxEventsRequest("https://events.mapbox.cn/events/v2")).toBe(true);
  });

  it("laesst andere Mapbox- und fremde Hosts durch", async () => {
    const { istMapboxEventsRequest } = await ladeHelfer();
    expect(istMapboxEventsRequest("https://api.mapbox.com/styles/v1/mapbox/streets-v12")).toBe(false);
    expect(istMapboxEventsRequest("https://a.tiles.mapbox.com/v4/x/1/2/3.vector.pbf")).toBe(false);
    expect(istMapboxEventsRequest("https://events.mapbox.com.evil.example/x")).toBe(false);
    expect(istMapboxEventsRequest("/api/feed")).toBe(false);
  });
});

describe("sperreMapboxTelemetrie", () => {
  it("verwirft Events-Requests ohne Netzwerkzugriff und antwortet mit 204", async () => {
    const { sperreMapboxTelemetrie } = await ladeHelfer();
    sperreMapboxTelemetrie();
    const antwort = await fetch(
      new Request("https://events.mapbox.com/events/v2?access_token=pk.x", { method: "POST", body: "[]" }),
    );
    expect(antwort.ok).toBe(true);
    expect(antwort.status).toBe(204);
    expect(originalFetch).not.toHaveBeenCalled();
  });

  it("reicht alle anderen Requests unveraendert durch", async () => {
    const { sperreMapboxTelemetrie } = await ladeHelfer();
    sperreMapboxTelemetrie();
    const init = { method: "GET" };
    await fetch("https://api.mapbox.com/styles/v1/mapbox/streets-v12", init);
    expect(originalFetch).toHaveBeenCalledWith("https://api.mapbox.com/styles/v1/mapbox/streets-v12", init);
  });

  it("wickelt fetch nur einmal ein, auch bei wiederholtem Aufruf", async () => {
    const { sperreMapboxTelemetrie } = await ladeHelfer();
    sperreMapboxTelemetrie();
    const gewickelt = globalThis.fetch;
    sperreMapboxTelemetrie();
    expect(globalThis.fetch).toBe(gewickelt);
  });
});

describe("richteMapboxEin", () => {
  it("setzt das Token und aktiviert die Sperre", async () => {
    const { richteMapboxEin } = await ladeHelfer();
    richteMapboxEin("pk.test");
    expect(mapboxStub.accessToken).toBe("pk.test");
    await fetch("https://events.mapbox.com/events/v2", { method: "POST", body: "[]" });
    expect(originalFetch).not.toHaveBeenCalled();
  });
});
