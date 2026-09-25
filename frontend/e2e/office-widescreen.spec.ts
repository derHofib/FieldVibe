import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Ergaenzung zu apple-redesign.spec.ts (das nur eine Office-Seite bei
 * 1440x900 prueft): alle eigenstaendigen Desktop-Ansichten
 * (office/OfficeApp.tsx, "Eigenstaendige Desktop-Ansichten"-Block) bei
 * einem echten Grossbildschirm (1920x1080) -- horizontaler Overflow und
 * axe-core-Befunde. Die restlichen Office-Routen sind bewusst schmale,
 * von der Feld-App uebernommene Formular-/Detailseiten (SchmaleSpalte in
 * OfficeApp.tsx) und deshalb hier nicht relevant.
 */

const ADMIN = { email: "admin@mueller.example.de", password: "Handwerk123!" };

const PAGES = [
  { path: "/vorgaenge", name: "vorgaenge" },
  { path: "/dispo", name: "dispo" },
  { path: "/rechnungen", name: "rechnungen" },
  { path: "/angebote", name: "angebote" },
  { path: "/auswertung", name: "auswertung" },
  { path: "/postfach", name: "postfach" },
  { path: "/boards", name: "boards" },
  { path: "/projekte", name: "projekte" },
  { path: "/auftraege", name: "auftraege" },
];

async function login(page: Page) {
  await page.goto("/login?office=1");
  await page.locator('input[type="email"]').fill(ADMIN.email);
  await page.locator('input[type="password"]').fill(ADMIN.password);
  await page.getByRole("button", { name: /Anmelden/ }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
}

test.describe("Office Grossbildschirm-Check (1920x1080)", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  for (const p of PAGES) {
    test(p.name, async ({ page }) => {
      await login(page);
      await page.goto(p.path);
      await page.waitForTimeout(1000);

      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));

      await page.screenshot({
        path: `e2e-screenshots/office-wide-${p.name}.png`,
        fullPage: false,
      });

      const results = await new AxeBuilder({ page }).analyze();
      // eslint-disable-next-line no-console
      console.log(`[axe ${p.name}] ${results.violations.length} Verstoesse`);
      for (const v of results.violations) {
        // eslint-disable-next-line no-console
        console.log(`  - ${v.id} (${v.impact}): ${v.help} -- ${v.nodes.length}x`);
      }

      expect(overflow.scrollWidth - overflow.clientWidth, "kein horizontaler Overflow bei 1920px").toBeLessThanOrEqual(2);
      expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
    });
  }
});
