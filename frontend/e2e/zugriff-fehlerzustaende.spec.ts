import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Rechte-Sichtbarkeit und Fehlerzustaende (Paket 6.2): was ein Techniker nicht
 * darf, taucht in den Menues nicht auf und endet per Deep-Link auf der
 * "Kein Zugriff"-Seite; unbekannte Routen/Datensaetze zeigen 404 bzw. den
 * Fehlerzustand statt "Laedt...". Braucht den Seed-Stand (python -m app.seed)
 * und einen laufenden Backend-Stack, wie apple-redesign.spec.ts.
 */

const TECHNIKER = { email: "technik1@mueller.example.de", password: "Handwerk123!" };

// "Anlagen-Zusatzfelder" fehlt hier bewusst: technik1 hat im Seed kunden.sehen,
// der Eintrag ist fuer ihn also korrekt sichtbar (navSeiten.ts, key anlagen_felder).
const ADMIN_EINTRAEGE = ["Nutzer verwalten", "Account-Typen & Rechte", "Firmendaten & Integrationen"];

const UNBEKANNTE_UUID = "00000000-0000-4000-8000-000000000000";

async function login(page: Page, office = false) {
  await page.goto(office ? "/login?office=1" : "/login");
  await page.locator('input[type="email"]').fill(TECHNIKER.email);
  await page.locator('input[type="password"]').fill(TECHNIKER.password);
  await page.getByRole("button", { name: /Anmelden/ }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
}

/** SPA-interne Navigation (kein Reload), damit die Office-Flagge in sessionStorage erhalten bleibt. */
async function gehe(page: Page, pfad: string) {
  await page.evaluate((p) => {
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, pfad);
}

async function axeVerstoesse(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).exclude("iframe").analyze();
  for (const v of results.violations) {
    // eslint-disable-next-line no-console
    console.log(`[axe] ${label}: ${v.id} (${v.impact}) ${v.help} ${JSON.stringify(v.nodes[0]?.any[0]?.data)} -- ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  }
  return results.violations.map((v) => v.id);
}

function client4xxSammeln(page: Page) {
  const treffer: string[] = [];
  page.on("response", (r) => {
    const s = r.status();
    if (s >= 400 && s < 500 && r.url().includes("/api/")) treffer.push(`${s} ${r.request().method()} ${new URL(r.url()).pathname}`);
  });
  page.on("console", (m) => {
    if (m.type() === "error" && /status of 4\d\d/.test(m.text())) treffer.push(`console: ${m.text()}`);
  });
  return treffer;
}

test.describe("Techniker: Menues ohne Admin-Eintraege", () => {
  test("Feld-App: Mehr zeigt keine Verwaltungseintraege", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await page.goto("/mehr");
    await expect(page.getByRole("heading", { name: "Mehr" }).first()).toBeVisible();
    for (const text of ADMIN_EINTRAEGE) {
      await expect(page.getByText(text, { exact: true })).toHaveCount(0);
    }
  });

  test("Office: Seitenleiste zeigt keine Verwaltungseintraege", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, true);
    const nav = page.getByRole("navigation", { name: "Hauptnavigation" });
    await expect(nav).toBeVisible();
    // Workspace "Verwaltung" aufklappen, falls vorhanden: dort lagen die Eintraege.
    const verwaltung = page.getByRole("tab", { name: "Verwaltung" });
    if (await verwaltung.count()) await verwaltung.first().click();
    for (const text of ADMIN_EINTRAEGE) {
      await expect(nav.getByText(text, { exact: true })).toHaveCount(0);
    }
  });
});

test.describe("Techniker: Deep-Links und Fehlerzustaende (Feld-App)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const pfad of ["/accounts", "/account-typen", "/integrationen"]) {
    test(`Deep-Link ${pfad} zeigt Kein Zugriff`, async ({ page }) => {
      await login(page);
      await page.goto(pfad);
      await expect(page.getByText("Kein Zugriff", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Zur Startseite" })).toBeVisible();
    });
  }

  test("normale Navigation erzeugt keine 4xx", async ({ page }) => {
    await login(page);
    // Erst nach dem Login sammeln: der 401 des Refresh-Versuchs auf der Login-Seite ist erwartet.
    const treffer = client4xxSammeln(page);
    for (const pfad of ["/feed", "/mehr", "/neu", "/statistik"]) {
      await gehe(page, pfad);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main, #root").first()).toBeVisible();
    }
    expect(treffer).toEqual([]);
  });

  test("Login landet im Feed, nicht auf der 404-Seite", async ({ page }) => {
    await login(page);
    await expect(page).toHaveURL(/\/feed$/);
  });

  test("unbekannte Route zeigt die 404-Seite", async ({ page }) => {
    await login(page);
    await page.goto("/gibt-es-nicht");
    await expect(page.getByText("Seite nicht gefunden")).toBeVisible();
  });

  test("unbekannter Kunde zeigt Fehlerzustand statt Laedt", async ({ page }) => {
    await login(page);
    await page.goto(`/kunden/${UNBEKANNTE_UUID}`);
    const alert = page.getByRole("alert").filter({ hasText: "Der Kunde nicht gefunden oder kein Zugriff." });
    await expect(alert).toBeVisible();
    await expect(page.getByText("Lädt", { exact: false })).toHaveCount(0);
  });
});

test.describe("axe: Zustandsseiten", () => {
  for (const theme of ["light", "dark"] as const) {
    test.describe(`Feld-App (${theme})`, () => {
      test.use({ viewport: { width: 390, height: 844 } });

      test(`Feed, Kein Zugriff, 404, Kundenprofil-Fehler, Vorgangsdetail (${theme})`, async ({ page }) => {
        await page.addInitScript((t) => window.localStorage.setItem("ui.appearance", t), theme);
        await login(page);
        await page.waitForLoadState("networkidle");
        expect(await axeVerstoesse(page, `feed-${theme}`)).toEqual([]);

        await page.goto("/accounts");
        await expect(page.getByText("Kein Zugriff", { exact: true })).toBeVisible();
        expect(await axeVerstoesse(page, `kein-zugriff-${theme}`)).toEqual([]);

        await page.goto("/gibt-es-nicht");
        await expect(page.getByText("Seite nicht gefunden")).toBeVisible();
        expect(await axeVerstoesse(page, `404-${theme}`)).toEqual([]);

        await page.goto(`/kunden/${UNBEKANNTE_UUID}`);
        await expect(page.getByRole("alert")).toBeVisible();
        expect(await axeVerstoesse(page, `kundenprofil-fehler-${theme}`)).toEqual([]);

        await page.goto("/feed");
        await page.waitForLoadState("networkidle");
        // Karten navigieren per Klick (kein href): erste Vorgangskarte oeffnen.
        await page.getByText(/V-\d{4}/).first().click();
        await page.waitForURL(/\/vorgaenge\//);
        await page.waitForLoadState("networkidle");
        expect(await axeVerstoesse(page, `vorgangsdetail-${theme}`)).toEqual([]);
      });
    });

    test.describe(`Office (${theme})`, () => {
      test.use({ viewport: { width: 1440, height: 900 } });

      test(`Vorgaenge (${theme})`, async ({ page }) => {
        await page.addInitScript((t) => window.localStorage.setItem("ui.appearance", t), theme);
        await login(page, true);
        await gehe(page, "/vorgaenge");
        await page.waitForLoadState("networkidle");
        expect(await axeVerstoesse(page, `office-vorgaenge-${theme}`)).toEqual([]);
      });
    });
  }
});
