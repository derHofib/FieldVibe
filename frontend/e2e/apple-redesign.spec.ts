import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Phase D des Apple-Redesigns: Screenshot- und Axe-Smoke-Test fuer die
 * wichtigsten bereits umgestellten Screens jeder Oberflaeche (Super-Admin,
 * Feld-App, Office), je hell/dunkel. Kein voller Routen-Katalog (siehe
 * "Was offen bleibt" in docs/ui-redesign/REVIEW.md) -- das waere bei ueber
 * 100 Routen x 3 Breakpoints x 2 Themes nicht in vertretbarem Aufwand
 * automatisierbar; stattdessen die Screens, die in Abschnitt 4/5 des
 * Redesign-Auftrags explizit als Referenz genannt wurden.
 */

const SUPER_ADMIN = {
  email: "superadmin@fieldvibe.example.de",
  password: "SuperAdmin123!",
};

const TECHNIKER = {
  email: "technik1@mueller.example.de",
  password: "Handwerk123!",
};

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => {
    window.localStorage.setItem("ui.appearance", t);
  }, theme);
}

async function login(page: Page, creds: { email: string; password: string }) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(creds.email);
  await page.locator('input[type="password"]').fill(creds.password);
  await page.getByRole("button", { name: /Anmelden/ }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
}

async function checkA11y(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .exclude("iframe")
    .analyze();
  // eslint-disable-next-line no-console
  console.log(`[axe] ${label}: ${results.violations.length} Verstoesse`);
  for (const v of results.violations) {
    // eslint-disable-next-line no-console
    console.log(`  - ${v.id} (${v.impact}): ${v.help} -- ${v.nodes.length}x`);
    for (const n of v.nodes) {
      // eslint-disable-next-line no-console
      console.log(`      ${n.target.join(" ")} :: ${n.failureSummary?.replace(/\n/g, " ")}`);
    }
  }
  return results.violations;
}

for (const theme of ["light", "dark"] as const) {
  test.describe(`Super-Admin (${theme})`, () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test(`Dashboard + Seitenleiste (${theme})`, async ({ page }) => {
      await setTheme(page, theme);
      await login(page, SUPER_ADMIN);
      await expect(page.getByText("Field", { exact: false }).first()).toBeVisible();
      await page.screenshot({
        path: `e2e-screenshots/super-admin-dashboard-${theme}.png`,
        fullPage: false,
      });
      const violations = await checkA11y(page, `super-admin-dashboard-${theme}`);
      expect(violations.filter((v) => v.impact === "critical")).toEqual([]);
    });
  });

  test.describe(`Feld-App (${theme})`, () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test(`Feed + BottomNav (${theme})`, async ({ page }) => {
      await setTheme(page, theme);
      await login(page, TECHNIKER);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: `e2e-screenshots/feld-app-feed-${theme}.png`,
        fullPage: false,
      });
      const violations = await checkA11y(page, `feld-app-feed-${theme}`);
      expect(violations.filter((v) => v.impact === "critical")).toEqual([]);
    });
  });

  test.describe(`Office (${theme})`, () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test(`Vorgangsliste (${theme})`, async ({ page }) => {
      await setTheme(page, theme);
      await page.goto("/login?office=1");
      await page.locator('input[type="email"]').fill(TECHNIKER.email);
      await page.locator('input[type="password"]').fill(TECHNIKER.password);
      await page.getByRole("button", { name: /Anmelden/ }).click();
      await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
      await page.waitForTimeout(500);
      await page.screenshot({
        path: `e2e-screenshots/office-vorgaenge-${theme}.png`,
        fullPage: false,
      });
      const violations = await checkA11y(page, `office-vorgaenge-${theme}`);
      expect(violations.filter((v) => v.impact === "critical")).toEqual([]);
    });
  });
}
