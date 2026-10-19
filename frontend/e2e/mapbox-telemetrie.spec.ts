import { expect, test, type Page } from "@playwright/test";

/**
 * Mapbox-Telemetrie (events.mapbox.com, DSGVO): rendert die Feed-Kartenansicht
 * und prueft, dass kein einziger Request an den Events-Host ausgeloest wird,
 * waehrend Style- und Tile-Requests weiter laufen. Alle Mapbox-Hosts sind per
 * page.route gemockt -- kein echter Mapbox-Zugriff, kein echtes Token noetig.
 *
 * Voraussetzung: laufender Dev-Stack mit Seed und einem syntaktisch gueltigen
 * Dummy-Token (mapbox-gl braucht "pk.<base64-JSON>.<sig>", sonst startet die
 * Karte gar nicht), z. B.
 *   VITE_MAPBOX_TOKEN=pk.eyJ1IjoiZHVtbXkifQ.ZHVtbXk npm run dev
 * E2E_BASE_URL zeigt auf das Frontend (Default http://localhost:5173).
 */

const ADMIN = { email: "admin@mueller.example.de", password: "Handwerk123!" };

// Minimaler Style mit einer Vektor-Quelle, damit mapbox-gl Tile-Requests
// ausloest, ohne dass echte Kartendaten noetig sind.
const MINIMAL_STYLE = {
  version: 8,
  sources: {
    test: { type: "vector", tiles: ["https://a.tiles.mapbox.com/v4/test/{z}/{x}/{y}.vector.pbf"] },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#eee" } },
    { id: "flaeche", type: "fill", source: "test", "source-layer": "x" },
  ],
};

async function login(page: Page) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(ADMIN.email);
  await page.locator('input[type="password"]').fill(ADMIN.password);
  await page.getByRole("button", { name: /Anmelden/ }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
}

test("Kartenansicht loest keine Requests an events.mapbox.com aus", async ({ page }) => {
  const mapboxRequests: string[] = [];
  page.on("request", (req) => {
    if (/(^|\.)mapbox\.c(om|n)$/.test(new URL(req.url()).hostname)) mapboxRequests.push(req.url());
  });

  await page.route(/^https?:\/\/([^/]+\.)?mapbox\.com\//, async (route) => {
    const url = route.request().url();
    if (url.includes("/styles/v1/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MINIMAL_STYLE) });
    } else {
      await route.fulfill({ status: 200, contentType: "application/octet-stream", body: "" });
    }
  });

  // Seed-Vorgaenge haben keine Koordinaten -- ohne Punkte zeigt die
  // Kartenansicht nur einen Leerzustand und mapbox-gl wird nie geladen.
  await page.route(/\/api\/feed(\?|$)/, async (route) => {
    const antwort = await route.fetch();
    const body = (await antwort.json()) as { items: Array<Record<string, unknown>> };
    body.items.forEach((c, i) => {
      c.geo_lat = 51.1 + i * 0.01;
      c.geo_lng = 10.4 + i * 0.01;
    });
    await route.fulfill({ response: antwort, json: body });
  });

  await login(page);
  await page.getByRole("button", { name: "Karte", exact: true }).click();
  await expect(page.locator("canvas.mapboxgl-canvas")).toBeVisible({ timeout: 15_000 });

  // mapbox-gl schreibt tiles.mapbox.com-URLs im Style auf api.mapbox.com/v4
  // um; die Events folgen erst nach dem ersten vollstaendigen Rendern.
  const istTile = (u: string) => /\/v4\//.test(u) || new URL(u).hostname.endsWith("tiles.mapbox.com");
  await expect.poll(() => mapboxRequests.filter(istTile).length, { timeout: 15_000 }).toBeGreaterThan(0);
  await page.waitForTimeout(3000);

  const events = mapboxRequests.filter((u) => new URL(u).hostname.startsWith("events."));
  const tiles = mapboxRequests.filter(istTile);
  const style = mapboxRequests.filter((u) => u.includes("/styles/v1/"));
  const session = mapboxRequests.filter((u) => u.includes("/map-sessions/"));
  // eslint-disable-next-line no-console
  console.log(`[mapbox] events=${events.length} tiles=${tiles.length} style=${style.length} session=${session.length}`);

  expect(events, `Telemetrie-Requests: ${events.join(", ")}`).toHaveLength(0);
  expect(tiles.length).toBeGreaterThan(0);
  expect(style.length).toBeGreaterThan(0);
  // Der Session-Aufruf (Abrechnung) darf von der Sperre nicht mitgerissen werden.
  expect(session.length).toBeGreaterThan(0);
});
