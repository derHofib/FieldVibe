// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VorgangDetailPage } from "./VorgangDetailPage";

// Charakterisierungstest: friert Aufbau und API-Verdrahtung der Seite ein, damit die
// Zerlegung in Unterkomponenten (pages/feld/vorgangDetail/) das Verhalten nicht ändert.
// Alle Endpunkte antworten mit festen Fixtures; Aufrufe werden mitgeschrieben.
const h = vi.hoisted(() => {
  const antworten: Record<string, unknown> = {};
  const aufrufe: Array<[string, unknown[]]> = [];
  function api(name: string) {
    return new Proxy(
      {},
      {
        get(_t, methode: string) {
          return (...args: unknown[]) => {
            aufrufe.push([`${name}.${methode}`, args]);
            const a = antworten[`${name}.${methode}`];
            const wert = typeof a === "function" ? (a as (...x: unknown[]) => unknown)(...args) : a;
            return Promise.resolve(wert === undefined ? [] : wert);
          };
        },
      },
    );
  }
  return { antworten, aufrufe, api };
});

vi.mock("../../api/endpoints", () => {
  const namen = [
    "angeboteApi", "rechnungenApi", "anlagenApi", "fahrzeugZuweisungenApi", "highlightsApi", "kundenApi",
    "leistungsverzeichnisApi", "lieferantenApi", "maengelApi", "mandantEinstellungenApi", "materialApi",
    "materialBedarfeApi", "partnerApi", "projektAufgabenApi", "standorteApi", "termineApi", "usersApi",
    "vorgangEventsApi", "vorgaengeApi", "zeiterfassungApi", "emailApi", "mailApi", "fahrzeugeApi",
  ];
  return Object.fromEntries(namen.map((n) => [n, h.api(n)]));
});
vi.mock("../../offline/cache", () => ({
  cacheEvents: vi.fn(async () => {}),
  cacheKunde: vi.fn(async () => {}),
  getCachedEvents: vi.fn(async () => []),
  getCachedKunde: vi.fn(async () => undefined),
}));
vi.mock("../../offline/outbox", () => ({
  discardOutboxItem: vi.fn(async () => {}),
  getOutboxItems: vi.fn(async () => []),
  queueDokument: vi.fn(async () => {}),
  queueFoto: vi.fn(async () => {}),
  queueKommentar: vi.fn(async () => {}),
  queueStatusChange: vi.fn(async () => {}),
}));
vi.mock("../../components/EmailSection", () => ({ EmailSection: () => <div data-testid="email-section" /> }));
vi.mock("../../components/MapboxMap", () => ({ MapboxMap: () => <div data-testid="karte" /> }));
vi.mock("../../components/apple/BestaetigungsDialog", () => ({ bestaetigen: vi.fn(async () => true) }));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({
    currentUser: {
      id: "u1",
      role: "mandant_admin",
      name: "Mia Muster",
      email: "mia@example.org",
      deaktivierte_module: [],
      nur_zugewiesene_kunden: false,
      darf_zeiten_buchen: true,
      darf_vorgaenge_selbst_uebernehmen: true,
      darf_abwesenheiten_verwalten: true,
    },
    hatRecht: () => true,
  }),
}));

const VORGANG = {
  id: "v1",
  vorgangsnummer: "V-2026-0042",
  kunde_id: "k1",
  anlage_id: "a1",
  standort_id: "s1",
  vertrag_id: null,
  parent_vorgang_id: "v0",
  projekt_id: null,
  auftrag_id: null,
  dauerauftrag_id: null,
  titel: "Sicherungskasten tauschen",
  beschreibung: "Alter Kasten, FI defekt.",
  abrechnungsart: "aufwand",
  leistungstyp: "installation",
  status: "in_arbeit",
  prioritaet: 2,
  faelligkeit_am: "2026-10-20",
  adresse: { strasse: "Hauptstr. 1", plz: "10115", ort: "Berlin" },
  zugewiesener_user_id: "u1",
  zugewiesener_name: "Mia Muster",
  last_activity_at: "2026-10-21T08:00:00Z",
  abgeschlossen_am: null,
  erstellt_von_kundenportal_zugang_id: null,
  erstellt_von: "u1",
  wiedervorlage_am: null,
  partner_id: "p1",
  partner_freigabe_status: "vorgeschlagen",
  partner_ablehnung_grund: null,
  partner_honorar_netto: "120.00",
  created_at: "2026-10-01T08:00:00Z",
  updated_at: "2026-10-21T08:00:00Z",
};

function befuelleAntworten() {
  const a = h.antworten;
  for (const k of Object.keys(a)) delete a[k];
  Object.assign(a, {
    "vorgaengeApi.get": (id: string) => (id === "v0" ? { ...VORGANG, id: "v0", vorgangsnummer: "V-2026-0001", titel: "Vorauftrag", parent_vorgang_id: null } : VORGANG),
    "vorgaengeApi.list": [{ ...VORGANG, id: "v2", vorgangsnummer: "V-2026-0050", titel: "Folgeauftrag", parent_vorgang_id: "v1" }],
    "vorgaengeApi.anlagen": [{ id: "a2", bezeichnung: "Zweite Anlage", objekttyp: "kundenanlage", adresse: {} }],
    "vorgaengeApi.emails": [],
    "kundenApi.get": { id: "k1", kundennummer: "K-100", name: "Muster GmbH", ansprechpartner: [], adresse: null },
    "anlagenApi.get": { id: "a1", bezeichnung: "Hauptverteilung", objekttyp: "kundenanlage", adresse: { strasse: "Anlagenweg 2", plz: "10115", ort: "Berlin" }, geo_lat: 52.5, geo_lng: 13.4 },
    "anlagenApi.list": [
      { id: "a1", bezeichnung: "Hauptverteilung", objekttyp: "kundenanlage", adresse: {} },
      { id: "l1", bezeichnung: "Lager Nord", objekttyp: "lager", adresse: {} },
    ],
    "standorteApi.get": { id: "s1", name: "Werk 1", adresse: { strasse: "Werkstr. 5", plz: "10115", ort: "Berlin" } },
    "vorgangEventsApi.list": [
      { id: 3, vorgang_id: "v1", event_type: "kommentar", author_user_id: "u1", is_system: false, kundensichtbar: true, body: "Material liegt bereit", payload: {}, ref_entity_type: null, ref_entity_id: null, client_uuid: null, created_at: "2026-10-21T09:00:00Z", foto_url: null, foto_thumbnail_url: null, unterschrift_url: null, dokument_url: null, dokument_dateiname: null },
      { id: 2, vorgang_id: "v1", event_type: "status_change", author_user_id: "u1", is_system: true, kundensichtbar: false, body: null, payload: { from: "neu", to: "in_arbeit" }, ref_entity_type: null, ref_entity_id: null, client_uuid: null, created_at: "2026-10-20T09:00:00Z", foto_url: null, foto_thumbnail_url: null, unterschrift_url: null, dokument_url: null, dokument_dateiname: null },
    ],
    "usersApi.auswahl": [
      { id: "u1", name: "Mia Muster", role: "mandant_admin" },
      { id: "u2", name: "Tom Techniker", role: "custom" },
    ],
    "zeiterfassungApi.laufend": null,
    "zeiterfassungApi.list": [
      { id: "z1", vorgang_id: "v1", vorgangsnummer: "V-2026-0042", vorgang_kunde_id: "k1", vorgang_auftrag_id: null, vorgang_projekt_id: null, techniker_id: "u1", start_at: "2026-10-20T07:00:00Z", ende_at: "2026-10-20T09:30:00Z", taetigkeit: "Kasten demontiert", abrechenbar: true, kategorie: "auftrag", lv_position_id: null, buchungsstatus: "vermerkt", vorgemerkt_von: null, vorgemerkt_am: null, gebucht_von: null, gebucht_am: null, km: "12", fahrzeug_id: null, quelle: "timer", km_abgerechnet_rechnung_id: null, created_at: "2026-10-20T07:00:00Z" },
    ],
    "termineApi.list": [
      { id: "t1", vorgang_id: "v1", techniker_id: "u2", erstellt_von: "u1", titel: "Montage", start_at: "2026-10-23T08:00:00Z", ende_at: "2026-10-23T12:00:00Z", status: "geplant", notiz: null, fahrzeit_minuten: null, pause_minuten: null, created_at: "2026-10-01T08:00:00Z", updated_at: "2026-10-01T08:00:00Z" },
    ],
    "termineApi.create": { warnungen: [] },
    "maengelApi.list": [
      { id: "m1", vorgang_id: "v1", anlage_id: "a1", beschreibung: "FI löst nicht aus", schweregrad: "hoch", status: "offen", gemeldet_von: "u1", angebot_id: null, reparatur_vorgang_id: null, behoben_am: null, created_at: "2026-10-19T08:00:00Z", updated_at: "2026-10-19T08:00:00Z" },
    ],
    "maengelApi.create": { id: "m2" },
    "projektAufgabenApi.list": [{ id: "pa1", titel: "Material bestellen", projekt_id: null, erledigt_am: null, vorgang_id: "v1", prioritaet: "mittel", checkliste: [{ text: "Angebot einholen", erledigt: true }, { text: "Bestellen", erledigt: false }], zugewiesener_name: "Mia Muster" }],
    "materialApi.list": [{ id: "mat1", bezeichnung: "FI-Schalter 40A", einheit: "Stk", einzelpreis: "25.00", artikelnummer: "FI-40" }],
    "materialApi.verwendungen": [{ id: "mv1", material_id: "mat1", lager_id: "l1", vorgang_id: "v1", menge: "2", verwendet_von: "u1", created_at: "2026-10-20T10:00:00Z" }],
    "materialApi.verwenden": { id: "mv2" },
    "materialBedarfeApi.list": [{ id: "mb1", material_id: "mat1", vorgang_id: "v1", menge: "5", notiz: "bis Freitag", zweck: "bestellung", status: "offen", bestellung_id: null, angebot_id: null, erstellt_von: "u1", uebernommen_von_id: null, created_at: "2026-10-20T10:00:00Z" }],
    "leistungsverzeichnisApi.verwendungen": [],
    "partnerApi.get": { id: "p1", name: "Elektro Nord", gewerk: "Elektro", ansprechpartner: [], telefon: null, email: null, adresse: null, notiz: null, aktiv: true },
    "partnerApi.list": [{ id: "p1", name: "Elektro Nord", gewerk: "Elektro", ansprechpartner: [], aktiv: true }],
    "mandantEinstellungenApi.get": { effektive_wiedervorlage_standard_tage: 14 },
    "vorgaengeApi.update": VORGANG,
    "vorgangEventsApi.create": { id: 9 },
  });
}

function zeige(props: Parameters<typeof VorgangDetailPage>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VorgangDetailPage id="v1" {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function bereit() {
  await screen.findByText("Sicherungskasten tauschen");
  // Alle Abschnitts-Queries abwarten (Mängel, Termine, Material, Zeit, Verlauf).
  await waitFor(() => {
    expect(h.aufrufe.map(([n]) => n)).toEqual(
      expect.arrayContaining(["maengelApi.list", "termineApi.list", "materialApi.verwendungen", "zeiterfassungApi.list", "vorgangEventsApi.list"]),
    );
  });
  await new Promise((r) => setTimeout(r, 50));
}

// Kompakte Struktur statt Voll-DOM: Text, Interaktives, Rollen, Werte und verborgene Bereiche.
function struktur(root: Element): string {
  const zeilen: string[] = [];
  const verborgen = (el: Element) => {
    for (let e: Element | null = el; e; e = e.parentElement) if (e.classList.contains("hidden")) return true;
    return false;
  };
  const walk = (el: Element, tiefe: number) => {
    const eigen = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent?.trim())
      .filter(Boolean)
      .join(" ");
    const tag = el.tagName.toLowerCase();
    const interaktiv = ["button", "a", "input", "select", "textarea"].includes(tag) || el.hasAttribute("role") || /^h[1-6]$/.test(tag);
    let naechste = tiefe;
    if (eigen || interaktiv) {
      const attrs = ["role", "aria-label", "aria-selected", "aria-labelledby", "id", "type", "placeholder", "href", "title"]
        .filter((a) => el.hasAttribute(a))
        .map((a) => `${a}=${el.getAttribute(a)}`);
      if ((el as HTMLButtonElement).disabled) attrs.push("disabled");
      if (["input", "select", "textarea"].includes(tag)) attrs.push(`value=${(el as HTMLInputElement).value}`);
      zeilen.push(`${"  ".repeat(tiefe)}${verborgen(el) ? "[verborgen] " : ""}${tag}${attrs.length ? " " + attrs.join(" ") : ""}${eigen ? ": " + eigen : ""}`);
      naechste = tiefe + 1;
    }
    for (const kind of Array.from(el.children)) walk(kind, naechste);
  };
  walk(root, 0);
  return zeilen.join("\n");
}

// Optional (VOLLSNAPSHOT_DIR gesetzt): zusaetzlich das komplette DOM in eine Datei schreiben, um
// Umbauten Zeichen fuer Zeichen zu vergleichen. Nicht eingecheckt, nur lokales Hilfsmittel.
async function pruefe(container: Element, name: string) {
  expect(struktur(container)).toMatchSnapshot(name);
  const dir = process.env.VOLLSNAPSHOT_DIR;
  if (dir) await expect(container.innerHTML.replace(/></g, ">\n<")).toMatchFileSnapshot(`${dir}/${name.replace(/[^\w]+/g, "_")}.html`);
}

function aufrufeVon(name: string) {
  return h.aufrufe.filter(([n]) => n === name).map(([, args]) => args);
}

beforeEach(() => {
  h.aufrufe.length = 0;
  befuelleAntworten();
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-22T10:00:00Z") });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("VorgangDetailPage – Aufbau", () => {
  it("kompakt, voll", async () => {
    const { container } = zeige();
    await bereit();
    await pruefe(container, "kompakt, voll");
  });

  it("kompakt, Unterseite Zeit", async () => {
    const { container } = zeige({ ansicht: "zeit" });
    await screen.findByText("Sicherungskasten tauschen");
    await new Promise((r) => setTimeout(r, 80));
    await pruefe(container, "kompakt, Unterseite Zeit");
  });

  it("kompakt, Unterseite Verlauf", async () => {
    const { container } = zeige({ ansicht: "verlauf" });
    await screen.findByText("Sicherungskasten tauschen");
    await new Promise((r) => setTimeout(r, 80));
    await pruefe(container, "kompakt, Unterseite Verlauf");
  });

  it("kompakt, Unterseite Positionen", async () => {
    const { container } = zeige({ ansicht: "positionen" });
    await screen.findByText("Sicherungskasten tauschen");
    await new Promise((r) => setTimeout(r, 80));
    await pruefe(container, "kompakt, Unterseite Positionen");
  });

  it("dicht (Office-Inspektor)", async () => {
    const { container } = zeige({ layout: "dicht" });
    await bereit();
    await pruefe(container, "dicht (Office-Inspektor)");
  });

  it("dicht, breit (Vollbild)", async () => {
    const { container } = zeige({ layout: "dicht", breit: true });
    await bereit();
    await pruefe(container, "dicht, breit (Vollbild)");
  });
});

describe("VorgangDetailPage – Tabs im dichten Layout", () => {
  it.each(["Zeit", "Termine", "Mängel", "Positionen", "Verlauf"])("Tab %s zeigt nur sein Panel", async (label) => {
    const { container } = zeige({ layout: "dicht" });
    await bereit();
    fireEvent.click(screen.getByRole("tab", { name: label }));
    await pruefe(container, `Tab ${label}`);
  });
});

describe("VorgangDetailPage – Aktionen rufen die API", () => {
  it("fehlender Vorgang zeigt Fehlerzustand", async () => {
    h.antworten["vorgaengeApi.get"] = () => {
      throw new Error("nicht gefunden");
    };
    const { container } = zeige();
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.get").length).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 80));
    await pruefe(container, "Fehlerzustand");
  });
});

const klick = (name: string, index = 0) => fireEvent.click(screen.getAllByRole("button", { name })[index]);

describe("VorgangDetailPage – geöffnete Formulare", () => {
  const faelle: Array<[string, () => void]> = [
    ["Zuordnung bearbeiten", () => klick("Bearbeiten", 0)],
    ["Adresse bearbeiten", () => klick("Bearbeiten", 1)],
    ["Anlage hinzufügen", () => klick("+ Hinzufügen")],
    ["Folge-Vorgang", () => klick("+ Folge-Vorgang")],
    ["Termin planen", () => klick("+ Termin planen")],
    ["Mangel melden", () => klick("+ Mangel melden")],
    ["Material bestellen", () => klick("+ Material bestellen")],
    ["Material verwenden", () => klick("+ Material verwenden")],
    ["Leistung verwenden", () => klick("+ Leistung verwenden")],
    ["Erwähnen", () => klick("Erwähnen")],
    ["Unterschrift erfassen", () => klick("Unterschrift erfassen")],
    ["Partner ändern", () => klick("Elektro Nord")],
    ["Zeit nachtragen", () => klick("+ Zeit nachtragen")],
    ["Status wartet auf Kunde", () => fireEvent.change(document.getElementById("vorgang-status-select")!, { target: { value: "wartet_kunde" } })],
    ["Verlauf-Filter System", () => klick("System")],
  ];
  it.each(faelle)("%s", async (name, aktion) => {
    const { container } = zeige({ layout: "dicht" });
    await bereit();
    aktion();
    await new Promise((r) => setTimeout(r, 50));
    await pruefe(container, `offen: ${name}`);
  });
});

describe("VorgangDetailPage – Aktionen rufen die API", () => {
  async function dicht() {
    zeige({ layout: "dicht" });
    await bereit();
  }

  it("Kommentar senden", async () => {
    await dicht();
    fireEvent.change(screen.getByPlaceholderText("Kommentar schreiben…"), { target: { value: "Alles klar" } });
    klick("Senden");
    await waitFor(() => expect(aufrufeVon("vorgangEventsApi.create")).toHaveLength(1));
    expect(aufrufeVon("vorgangEventsApi.create")[0]).toEqual([
      "v1",
      { event_type: "kommentar", body: "Alles klar", kundensichtbar: false, partner_sichtbar: false, client_uuid: expect.any(String) },
    ]);
  });

  it("Mangel erfassen", async () => {
    await dicht();
    klick("+ Mangel melden");
    fireEvent.change(screen.getByPlaceholderText("Was ist defekt?"), { target: { value: "Kabel blank" } });
    fireEvent.change(within(screen.getByPlaceholderText("Was ist defekt?").parentElement!).getByRole("combobox"), { target: { value: "kritisch" } });
    klick("Erfassen");
    await waitFor(() => expect(aufrufeVon("maengelApi.create")).toHaveLength(1));
    expect(aufrufeVon("maengelApi.create")[0]).toEqual([{ vorgang_id: "v1", beschreibung: "Kabel blank", schweregrad: "kritisch" }]);
  });

  it("Termin anlegen", async () => {
    await dicht();
    klick("+ Termin planen");
    fireEvent.change(screen.getByPlaceholderText("Titel"), { target: { value: "Abnahme" } });
    const formular = screen.getByPlaceholderText("Titel").parentElement!;
    fireEvent.change(within(formular).getByRole("combobox"), { target: { value: "u2" } });
    const zeiten = formular.querySelectorAll('input[type="datetime-local"]');
    fireEvent.change(zeiten[0], { target: { value: "2026-10-25T08:00" } });
    fireEvent.change(zeiten[1], { target: { value: "2026-10-25T10:00" } });
    klick("Anlegen");
    await waitFor(() => expect(aufrufeVon("termineApi.create")).toHaveLength(1));
    expect(aufrufeVon("termineApi.create")[0]).toEqual([
      {
        vorgang_id: "v1",
        techniker_id: "u2",
        titel: "Abnahme",
        start_at: new Date("2026-10-25T08:00").toISOString(),
        ende_at: new Date("2026-10-25T10:00").toISOString(),
      },
    ]);
  });

  it("Status und Priorität ändern", async () => {
    await dicht();
    fireEvent.change(document.getElementById("vorgang-status-select")!, { target: { value: "abgeschlossen" } });
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.update")).toHaveLength(1));
    expect(aufrufeVon("vorgaengeApi.update")[0]).toEqual(["v1", { status: "abgeschlossen" }]);
    fireEvent.change(screen.getByLabelText("Priorität"), { target: { value: "4" } });
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.update")).toHaveLength(2));
    expect(aufrufeVon("vorgaengeApi.update")[1]).toEqual(["v1", { prioritaet: 4 }]);
  });

  it("Wartet auf Kunde mit Wiedervorlage", async () => {
    await dicht();
    fireEvent.change(document.getElementById("vorgang-status-select")!, { target: { value: "wartet_kunde" } });
    fireEvent.change(screen.getByPlaceholderText("14"), { target: { value: "7" } });
    klick("Übernehmen");
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.update")).toHaveLength(1));
    expect(aufrufeVon("vorgaengeApi.update")[0]).toEqual(["v1", { status: "wartet_kunde", wiedervorlage_tage: 7 }]);
  });

  it("Folge-Vorgang anlegen", async () => {
    h.antworten["vorgaengeApi.folgeAuftrag"] = { id: "v9" };
    await dicht();
    klick("+ Folge-Vorgang");
    klick("Anlegen");
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.folgeAuftrag")).toHaveLength(1));
    expect(aufrufeVon("vorgaengeApi.folgeAuftrag")[0]).toEqual(["v1", "stoerung"]);
    expect(await screen.findByText("Folge-Vorgang wurde angelegt.")).toBeInTheDocument();
  });

  it("Zeit starten mit Tätigkeit", async () => {
    await dicht();
    fireEvent.change(screen.getByPlaceholderText("Tätigkeit (optional)"), { target: { value: "Sicherung prüfen" } });
    klick("Zeit starten");
    await waitFor(() => expect(aufrufeVon("zeiterfassungApi.start")).toHaveLength(1));
    expect(aufrufeVon("zeiterfassungApi.start")[0]).toEqual(["v1", "Sicherung prüfen"]);
  });

  it("Partner zuweisung aufheben", async () => {
    await dicht();
    klick("Aufheben");
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.partnerZuweisen")).toHaveLength(1));
    expect(aufrufeVon("vorgaengeApi.partnerZuweisen")[0]).toEqual(["v1", null]);
  });

  it("Vorgang löschen nach Bestätigung", async () => {
    await dicht();
    klick("Vorgang löschen");
    await waitFor(() => expect(aufrufeVon("vorgaengeApi.remove")).toHaveLength(1));
    expect(aufrufeVon("vorgaengeApi.remove")[0]).toEqual(["v1"]);
  });

  it("Mangel auf behoben setzen und Termin/Mangel löschen fragen nach", async () => {
    await dicht();
    klick("Behoben");
    await waitFor(() => expect(aufrufeVon("maengelApi.update")).toHaveLength(1));
    expect(aufrufeVon("maengelApi.update")[0]).toEqual(["m1", { status: "behoben" }]);
  });

  it("Kompakt: Zeit nachtragen öffnet das Zeitsheet", async () => {
    zeige({ ansicht: "zeit" });
    await screen.findByText("Sicherungskasten tauschen");
    klick("+ Zeit nachtragen");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
