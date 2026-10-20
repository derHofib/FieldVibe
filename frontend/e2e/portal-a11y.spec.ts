import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Barrierefreiheit (BFSG / WCAG 2.1 AA) des Kundenportals mit axe-core.
 *
 * Laeuft ohne Backend: jede /api/-Anfrage wird per page.route mit festen
 * Daten beantwortet (Muster wie mapbox-telemetrie.spec.ts), der Login-Zustand
 * kommt ueber den localStorage-Schluessel des Kundenportals. Gegen einen
 * Produktions-Build testen, nicht gegen `vite dev`:
 *   npm run build && npx vite preview --host localhost --port 4173
 *   E2E_BASE_URL=http://localhost:4173 npx playwright test portal-a11y
 *
 * `serious`/`critical` lassen den Test scheitern, kleinere Befunde werden nur
 * geloggt. Jede Seite wird hell und dunkel geprueft.
 */

const ID = {
  vorgang: "11111111-1111-4111-8111-111111111111",
  angebotVersendet: "22222222-2222-4222-8222-222222222221",
  angebotAngenommen: "22222222-2222-4222-8222-222222222222",
  angebotB2b: "22222222-2222-4222-8222-222222222223",
  angebotWiderrufen: "22222222-2222-4222-8222-222222222224",
  rechnung: "33333333-3333-4333-8333-333333333333",
};

const POSITIONEN = [
  { id: "p1", position: 1, beschreibung: "Heizkörper tauschen", menge: "2.00", einheit: "Stk", einzelpreis: "100.00", gesamt: "200.00" },
  { id: "p2", position: 2, beschreibung: "Montage", menge: "3.00", einheit: "Std", einzelpreis: "50.00", gesamt: "150.00" },
];

const BELEHRUNG_TEXT =
  "PLATZHALTER - von Rechtsberatung prüfen. Kein rechtsgeprüfter Text.\n\nWiderrufsrecht\nSie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen.\n\nFolgen des Widerrufs\nWenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen zurückzuzahlen.";

function angebot(id: string, abweichung: Record<string, unknown> = {}) {
  return {
    id,
    angebotsnummer: "A-2026-0001",
    status: "versendet",
    mwst_satz: "19.00",
    gueltig_bis: "2026-12-31",
    versendet_am: "2026-10-01T08:00:00Z",
    angenommen_am: null,
    abgelehnt_am: null,
    widerrufen_am: null,
    created_at: "2026-10-01T08:00:00Z",
    positionen: POSITIONEN,
    gesamt_netto: "350.00",
    gesamt_brutto: "416.50",
    ist_abgelaufen: false,
    fassung_sha256: "a".repeat(64),
    verbraucherschutz: false,
    widerruf_moeglich: false,
    widerruf_frist_bis: null,
    widerruf_hinweis: null,
    nachweis_referenz: null,
    ...abweichung,
  };
}

const ANGEBOTE: Record<string, ReturnType<typeof angebot>> = {
  [ID.angebotVersendet]: angebot(ID.angebotVersendet, { verbraucherschutz: true }),
  [ID.angebotAngenommen]: angebot(ID.angebotAngenommen, {
    status: "angenommen",
    verbraucherschutz: true,
    angenommen_am: "2026-10-18T09:30:00Z",
    widerruf_moeglich: true,
    widerruf_frist_bis: "2026-11-02T23:00:00Z",
    nachweis_referenz: "44444444-4444-4444-8444-444444444444",
  }),
  [ID.angebotB2b]: angebot(ID.angebotB2b, { angebotsnummer: "A-2026-0002" }),
  [ID.angebotWiderrufen]: angebot(ID.angebotWiderrufen, {
    status: "widerrufen",
    verbraucherschutz: true,
    angenommen_am: "2026-10-18T09:30:00Z",
    widerrufen_am: "2026-10-19T10:00:00Z",
    nachweis_referenz: "44444444-4444-4444-8444-444444444445",
  }),
};

const VORGANG = {
  id: ID.vorgang,
  vorgangsnummer: "V-2026-0042",
  titel: "Heizung fällt aus",
  beschreibung: "Die Heizung im Erdgeschoss bleibt kalt.",
  leistungstyp: "stoerung",
  status: "in_arbeit",
  faelligkeit_am: null,
  anlage_id: null,
  standort_id: null,
  abgeschlossen_am: null,
  last_activity_at: "2026-10-18T09:00:00Z",
  created_at: "2026-10-17T09:00:00Z",
  updated_at: "2026-10-18T09:00:00Z",
};

const RECHNUNG = {
  id: ID.rechnung,
  rechnungsnummer: "R-2026-0007",
  status: "versendet",
  betrag_netto: "350.00",
  mwst_satz: "19.00",
  betrag_brutto: "416.50",
  bezahlter_betrag: "0.00",
  offener_betrag: "416.50",
  ist_ueberfaellig: false,
  faellig_am: "2026-11-15",
  leistungsdatum: "2026-10-18",
  versendet_am: "2026-10-18T10:00:00Z",
  bezahlt_am: null,
  ist_storno: false,
  rechnungsart: "rechnung",
  gutschrift_grund: null,
  created_at: "2026-10-18T10:00:00Z",
  positionen: POSITIONEN,
};

const RECHTLICHES = {
  impressum_url: null,
  datenschutz_url: null,
  barrierefreiheit_url: null,
  barrierefreiheit_kontakt_email: "barrierefrei@mueller.example.de",
  barrierefreiheit_stand: "2026-10-19",
  anbieter: {
    name: "Elektro Müller GmbH",
    strasse: "Werkstr. 5",
    plz: "12345",
    ort: "Musterstadt",
    land: "DE",
    telefon: "0123 456",
    email: "info@mueller.example.de",
    website: null,
    geschaeftsfuehrung: "Max Müller",
    handelsregister: null,
    ust_idnr: null,
  },
};

const VERBRAUCHERSCHUTZ = {
  verbraucherschutz: true,
  widerrufsfrist_tage: 14,
  belehrung: { version: "platzhalter-v1", text: BELEHRUNG_TEXT, ist_platzhalter: true },
  widerrufsformular_text: "PLATZHALTER - von Rechtsberatung prüfen.\n\nMuster-Widerrufsformular\n...",
};

type Mock = unknown | ((route: Route) => unknown);

const MOCKS: Record<string, Mock> = {
  "/api/public/rechtliches": RECHTLICHES,
  "/api/kundenportal/auth/me": {
    zugang_id: "z1",
    kunde_id: "k1",
    kunde_name: "Familie Beispiel",
    name: "Erika Beispiel",
    email: "erika@example.de",
    portal_slug: "demo-slug",
  },
  "/api/kundenportal/auth/link/demo-slug": { kunde_name: "Familie Beispiel", mandant_name: "Elektro Müller", hat_logo: false },
  "/api/kundenportal/vorgaenge": [VORGANG],
  [`/api/kundenportal/vorgaenge/${ID.vorgang}`]: VORGANG,
  [`/api/kundenportal/vorgaenge/${ID.vorgang}/events`]: [
    { id: 2, vorgang_id: ID.vorgang, event_type: "kommentar", is_system: false, body: "Wir kommen morgen vorbei.", created_at: "2026-10-18T09:00:00Z" },
    { id: 1, vorgang_id: ID.vorgang, event_type: "system", is_system: true, body: "Vorgang angelegt", created_at: "2026-10-17T09:00:00Z" },
  ],
  "/api/kundenportal/anfragen": [
    { id: "a1", standort_id: null, anlage_id: null, titel: "Wartung Heizung", beschreibung: null, leistungstyp: "wartung", status: "offen", ablehnungsgrund: null, created_at: "2026-10-10T09:00:00Z", updated_at: "2026-10-10T09:00:00Z" },
  ],
  "/api/kundenportal/standorte": [],
  "/api/kundenportal/anlagen": [],
  "/api/kundenportal/angebote": Object.values(ANGEBOTE),
  "/api/kundenportal/rechnungen": [RECHNUNG],
  [`/api/kundenportal/rechnungen/${ID.rechnung}`]: RECHNUNG,
  "/api/kundenportal/verbraucherschutz": VERBRAUCHERSCHUTZ,
};
for (const [id, a] of Object.entries(ANGEBOTE)) MOCKS[`/api/kundenportal/angebote/${id}`] = a;

async function mockApi(page: Page, extra: Record<string, Mock> = {}) {
  const tabelle = { ...MOCKS, ...extra };
  await page.route("**/api/**", async (route) => {
    const pfad = new URL(route.request().url()).pathname;
    const treffer = tabelle[pfad];
    if (treffer === undefined) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "nicht gemockt" }) });
      return;
    }
    const antwort = typeof treffer === "function" ? (treffer as (r: Route) => unknown)(route) : treffer;
    if (antwort === null) return; // Mock hat die Route selbst beantwortet
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(antwort) });
  });
}

async function vorbereiten(page: Page, theme: "light" | "dark", angemeldet: boolean) {
  await page.addInitScript(
    ([t, auth]) => {
      window.localStorage.setItem("ui.appearance", t as string);
      if (auth) {
        window.localStorage.setItem(
          "fieldvibe_kundenportal_auth_v1",
          JSON.stringify({ accessToken: "test-access", refreshToken: "test-refresh" }),
        );
      }
    },
    [theme, angemeldet],
  );
}

async function pruefeA11y(page: Page, label: string) {
  const ergebnis = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  // eslint-disable-next-line no-console
  console.log(`[axe] ${label}: ${ergebnis.violations.length} Verstoesse`);
  for (const v of ergebnis.violations) {
    // eslint-disable-next-line no-console
    console.log(`  - ${v.id} (${v.impact}): ${v.help} -- ${v.nodes.length}x`);
    for (const n of v.nodes.slice(0, 4)) {
      // eslint-disable-next-line no-console
      console.log(`      ${n.target.join(" ")} :: ${n.failureSummary?.replace(/\n/g, " ")}`);
    }
  }
  return ergebnis.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

type Seite = { name: string; pfad: string; angemeldet: boolean; bereit: RegExp | string };

const SEITEN: Seite[] = [
  { name: "login", pfad: "/portal/login", angemeldet: false, bereit: "Anmelden" },
  { name: "login-kundenlink", pfad: "/portal/l/demo-slug", angemeldet: false, bereit: /Willkommen, Familie Beispiel/ },
  { name: "vorgaenge", pfad: "/portal/vorgaenge", angemeldet: true, bereit: "Heizung fällt aus" },
  { name: "vorgang-detail", pfad: `/portal/vorgaenge/${ID.vorgang}`, angemeldet: true, bereit: "Wir kommen morgen vorbei." },
  { name: "anfragen", pfad: "/portal/anfragen", angemeldet: true, bereit: "Wartung Heizung" },
  { name: "angebote", pfad: "/portal/angebote", angemeldet: true, bereit: "A-2026-0001" },
  { name: "angebot-b2b-versendet", pfad: `/portal/angebote/${ID.angebotB2b}`, angemeldet: true, bereit: "Heizkörper tauschen" },
  { name: "rechnungen", pfad: "/portal/rechnungen", angemeldet: true, bereit: "R-2026-0007" },
  { name: "impressum", pfad: "/impressum?portal_slug=demo-slug", angemeldet: false, bereit: "Elektro Müller GmbH" },
  { name: "passwort-vergessen", pfad: "/portal/passwort-vergessen", angemeldet: false, bereit: "Link anfordern" },
  { name: "passwort-zuruecksetzen", pfad: "/portal/passwort-zuruecksetzen?token=abc", angemeldet: false, bereit: "Neues Passwort setzen" },
  { name: "angebot-b2c-versendet", pfad: `/portal/angebote/${ID.angebotVersendet}`, angemeldet: true, bereit: "Zahlungspflichtig beauftragen" },
  { name: "angebot-b2c-angenommen", pfad: `/portal/angebote/${ID.angebotAngenommen}`, angemeldet: true, bereit: "Vertrag widerrufen" },
  { name: "angebot-widerrufen", pfad: `/portal/angebote/${ID.angebotWiderrufen}`, angemeldet: true, bereit: /Sie haben diesen Vertrag am/ },
  { name: "angebot-widerruf-bestaetigen", pfad: `/portal/angebote/${ID.angebotAngenommen}/widerruf`, angemeldet: true, bereit: "Widerruf bestätigen" },
  { name: "barrierefreiheit", pfad: "/barrierefreiheit?portal_slug=demo-slug", angemeldet: false, bereit: "teilweise konform" },
];

for (const theme of ["light", "dark"] as const) {
  test.describe(`Kundenportal a11y (${theme})`, () => {
    // Ohne Service Worker, sonst umgeht dessen Cache die page.route-Mocks.
    test.use({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });

    for (const seite of SEITEN) {
      test(`${seite.name}`, async ({ page }) => {
        await vorbereiten(page, theme, seite.angemeldet);
        await mockApi(page);
        await page.goto(seite.pfad);
        await expect(page.getByText(seite.bereit).first()).toBeVisible({ timeout: 10_000 });
        await page.screenshot({ path: `e2e-screenshots/portal-${seite.name}-${theme}.png`, fullPage: true });
        expect(await pruefeA11y(page, `${seite.name}-${theme}`)).toEqual([]);
      });
    }
  });
}

test.describe("Kundenportal Bedienung per Tastatur", () => {
  test.use({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });

  test("B2C-Annahme: Button erst nach Kenntnisnahme, sendet Belehrungsversion und Fassung", async ({ page }) => {
    let gesendet: Record<string, unknown> | null = null;
    await vorbereiten(page, "light", true);
    await mockApi(page, {
      [`/api/kundenportal/angebote/${ID.angebotVersendet}`]: (route: Route) => {
        if (route.request().method() === "PATCH") {
          gesendet = route.request().postDataJSON();
          return { ...ANGEBOTE[ID.angebotVersendet], status: "angenommen" };
        }
        return ANGEBOTE[ID.angebotVersendet];
      },
    });
    await page.goto(`/portal/angebote/${ID.angebotVersendet}`);

    const knopf = page.getByRole("button", { name: "Zahlungspflichtig beauftragen", exact: true });
    await expect(knopf).toBeDisabled();
    // Die Belehrung ist ohne Klick lesbar.
    await expect(page.getByText("Wenn Sie diesen Vertrag widerrufen")).toBeVisible();
    await expect(page.getByRole("button", { name: "Muster-Widerrufsformular herunterladen" })).toBeVisible();

    const kenntnis = page.getByRole("checkbox", { name: /Widerrufsbelehrung gelesen/ });
    await kenntnis.focus();
    await page.keyboard.press("Space");
    await expect(knopf).toBeEnabled();
    await page.keyboard.press("Tab");
    await expect(knopf).toBeFocused();
    await page.keyboard.press("Enter");

    await expect.poll(() => gesendet).toEqual({
      status: "angenommen",
      bestaetigung: true,
      belehrung_version: "platzhalter-v1",
      fassung_sha256: "a".repeat(64),
    });
  });

  test("B2B-Annahme sendet nur den Status", async ({ page }) => {
    let gesendet: Record<string, unknown> | null = null;
    await vorbereiten(page, "light", true);
    await mockApi(page, {
      [`/api/kundenportal/angebote/${ID.angebotB2b}`]: (route: Route) => {
        if (route.request().method() === "PATCH") {
          gesendet = route.request().postDataJSON();
          return { ...ANGEBOTE[ID.angebotB2b], status: "angenommen" };
        }
        return ANGEBOTE[ID.angebotB2b];
      },
    });
    await page.goto(`/portal/angebote/${ID.angebotB2b}`);
    await page.getByRole("button", { name: "Annehmen", exact: true }).click();
    await expect.poll(() => gesendet).toEqual({ status: "angenommen" });
  });

  test("Fehler der Annahme wird als Alert angesagt", async ({ page }) => {
    await vorbereiten(page, "light", true);
    await mockApi(page, {
      [`/api/kundenportal/angebote/${ID.angebotVersendet}`]: (route: Route) => {
        if (route.request().method() === "PATCH") {
          void route.fulfill({
            status: 409,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Das Angebot wurde seit dem Laden der Seite geändert" }),
          });
          return null;
        }
        return ANGEBOTE[ID.angebotVersendet];
      },
    });
    await page.goto(`/portal/angebote/${ID.angebotVersendet}`);
    await page.getByRole("checkbox", { name: /Widerrufsbelehrung gelesen/ }).check();
    await page.getByRole("button", { name: "Zahlungspflichtig beauftragen", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("seit dem Laden der Seite geändert");
  });

  test("Widerruf: Button fuehrt auf die Bestaetigungsseite, erst dort wird gesendet", async ({ page }) => {
    let widerrufe = 0;
    await vorbereiten(page, "light", true);
    await mockApi(page, {
      [`/api/kundenportal/angebote/${ID.angebotAngenommen}/widerruf`]: () => {
        widerrufe += 1;
        return {
          ...ANGEBOTE[ID.angebotAngenommen],
          status: "widerrufen",
          widerrufen_am: "2026-10-19T10:00:00Z",
          widerruf_moeglich: false,
        };
      },
    });
    await page.goto(`/portal/angebote/${ID.angebotAngenommen}`);
    await page.getByRole("link", { name: "Vertrag widerrufen" }).click();
    await expect(page).toHaveURL(new RegExp(`/portal/angebote/${ID.angebotAngenommen}/widerruf$`));
    expect(widerrufe).toBe(0);

    const bestaetigen = page.getByRole("button", { name: "Widerruf bestätigen" });
    await bestaetigen.focus();
    await page.keyboard.press("Enter");

    const ueberschrift = page.getByRole("heading", { level: 1, name: "Ihr Widerruf ist eingegangen" });
    await expect(ueberschrift).toBeFocused();
    expect(widerrufe).toBe(1);
    expect(await pruefeA11y(page, "widerruf-eingegangen")).toEqual([]);
  });

  test("Skip-Link springt zum Inhalt", async ({ page }) => {
    await vorbereiten(page, "light", true);
    await mockApi(page);
    await page.goto("/portal/angebote");
    await expect(page.getByRole("heading", { level: 1, name: "Ihre Angebote" })).toBeVisible();
    await page.keyboard.press("Tab");
    const link = page.getByRole("link", { name: "Zum Inhalt springen" });
    await expect(link).toBeFocused();
    await expect(link).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#portal-inhalt")).toBeFocused();
  });

  test("Login-Fehler wird als Alert angesagt", async ({ page }) => {
    await vorbereiten(page, "light", false);
    await mockApi(page);
    await page.route("**/api/kundenportal/auth/login", (route) =>
      route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Ungültige Zugangsdaten" }) }),
    );
    await page.goto("/portal/login");
    await page.getByLabel("E-Mail").fill("x@example.de");
    await page.getByLabel("Passwort").fill("falsch");
    await page.getByRole("button", { name: "Anmelden" }).click();
    await expect(page.getByRole("alert")).toContainText("Ungültige Zugangsdaten");
  });

  test("Fusszeile verlinkt die Barrierefreiheitserklaerung", async ({ page }) => {
    await vorbereiten(page, "light", true);
    await mockApi(page);
    await page.goto("/portal/vorgaenge");
    await page.getByRole("link", { name: "Barrierefreiheit" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Erklärung zur Barrierefreiheit" })).toBeVisible();
    await expect(page.getByRole("link", { name: "barrierefrei@mueller.example.de" })).toBeVisible();
  });
});
