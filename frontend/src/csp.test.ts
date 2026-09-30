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
});
