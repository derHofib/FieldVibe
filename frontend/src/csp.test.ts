// Das Theme-Vorabskript in index.html ist in der CSP (Caddyfile) per
// sha256-Hash freigegeben statt per 'unsafe-inline'. Aendert sich das Skript,
// ohne dass der Hash nachgezogen wird, blockiert der Browser es (Aufblitzen
// im Dark Mode) -- dieser Test faengt die Drift ab.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("CSP-Hash des Inline-Skripts", () => {
  it("entspricht dem Hash im Caddyfile", () => {
    const html = readFileSync(path.resolve(__dirname, "../index.html"), "utf-8");
    const match = /<script>([\s\S]*?)<\/script>/.exec(html);
    expect(match).not.toBeNull();
    const hash = createHash("sha256").update(match![1]).digest("base64");
    const caddyfile = readFileSync(path.resolve(__dirname, "../../Caddyfile"), "utf-8");
    expect(caddyfile).toContain(`'sha256-${hash}'`);
  });

  it("erlaubt die Mapbox-Telemetrie (events.mapbox.com) nicht", () => {
    const caddyfile = readFileSync(path.resolve(__dirname, "../../Caddyfile"), "utf-8");
    const zeile = caddyfile.split("\n").find((l) => l.trim().startsWith("Content-Security-Policy-Report-Only "));
    expect(zeile).toBeDefined();
    expect(zeile).not.toContain("events.mapbox");
    expect(zeile).toContain("https://api.mapbox.com");
  });
});
