import { defineConfig, devices } from "@playwright/test";

/** Nur Chromium: in dieser Sandbox ist kein WebKit installiert (siehe
 * docs/ui-redesign/REVIEW.md, "Was offen bleibt"). Reale Cross-Browser-
 * Abdeckung (v. a. Safari/WebKit fuer die iOS-PWA-Zielgruppe der Feld-App)
 * muss auf einer Maschine mit `npx playwright install webkit` nachgeholt
 * werden. */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "e2e-report", open: "never" }]],
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: { executablePath: "/opt/pw-browsers/chromium" },
      },
    },
  ],
});
