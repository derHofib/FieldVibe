import { Ringpuffer } from "./ringpuffer";
import { schwaerzeText, STANDARD_CONFIG, type SchwaerzConfig } from "./schwaerzen";
import type { Breadcrumb } from "./typen";

export interface BreadcrumbOptionen {
  puffer: Ringpuffer<Breadcrumb>;
  schwaerz?: SchwaerzConfig;
}

const MAX_TEXT = 80;
const EINGABE_SELEKTOR = "input,textarea,select,[contenteditable]:not([contenteditable='false'])";

let deinstallieren: (() => void) | null = null;

function istEingabe(el: Element): boolean {
  return el.matches(EINGABE_SELEKTOR) || el.closest("[contenteditable]:not([contenteditable='false'])") !== null;
}

export function kurzSelektor(el: Element): string {
  const tag = el.tagName.toLowerCase();
  if (istEingabe(el)) {
    // Bewusst nur Struktur: kein Wert, keine Klassen/IDs, die Nutzerdaten enthalten koennten.
    const typ = el.getAttribute("type");
    const name = el.getAttribute("name");
    return `${tag}${typ ? `[type=${typ}]` : ""}${name ? `[name=${name}]` : ""}`;
  }
  const id = el.id && /^[\w-]+$/.test(el.id) ? `#${el.id}` : "";
  const klassen = Array.from(el.classList)
    .filter((k) => /^[\w-]{1,30}$/.test(k))
    .slice(0, 2)
    .map((k) => `.${k}`)
    .join("");
  return `${tag}${id}${klassen}`;
}

function sichtbarerText(el: Element, cfg: SchwaerzConfig): string | undefined {
  // Container mit Eingabefeldern (z. B. label oder ein anklickbares Formular-div) liefern
  // ueber textContent sonst select-Optionen bzw. Editor-Inhalt.
  if (istEingabe(el) || el.querySelector(EINGABE_SELEKTOR)) return undefined;
  const roh = (el.textContent ?? "").replace(/\s+/g, " ").trim() || el.getAttribute("aria-label") || "";
  if (!roh) return undefined;
  return schwaerzeText(roh.slice(0, MAX_TEXT), cfg);
}

function pfadVon(url: string): string {
  try {
    return new URL(url, location.href).pathname;
  } catch {
    return "";
  }
}

export function installBreadcrumbs(opt: BreadcrumbOptionen): void {
  if (deinstallieren) return;
  const cfg = opt.schwaerz ?? STANDARD_CONFIG;
  const push = (typ: Breadcrumb["typ"], ziel: string, text?: string) => {
    const b: Breadcrumb = { zeit: new Date().toISOString(), typ, ziel };
    if (text) b.text = text;
    opt.puffer.push(b);
  };

  const origPush = history.pushState;
  const origReplace = history.replaceState;
  const route = () => {
    try {
      push("route", location.pathname);
    } catch {
      // ignorieren
    }
  };
  history.pushState = function (this: History, ...args: Parameters<History["pushState"]>) {
    const r = origPush.apply(this, args);
    route();
    return r;
  };
  history.replaceState = function (this: History, ...args: Parameters<History["replaceState"]>) {
    const r = origReplace.apply(this, args);
    route();
    return r;
  };
  window.addEventListener("popstate", route);

  const onClick = (ev: MouseEvent) => {
    try {
      const ziel = ev.target;
      if (!(ziel instanceof Element)) return;
      const el = istEingabe(ziel) ? ziel : (ziel.closest("button,a,[role='button']") ?? ziel);
      push("klick", kurzSelektor(el), sichtbarerText(el, cfg));
    } catch {
      // ignorieren
    }
  };
  const onSubmit = (ev: Event) => {
    try {
      const form = ev.target;
      if (!(form instanceof HTMLFormElement)) return;
      // getAttribute statt form.action: ein Feld namens "action" ueberschattet die Property.
      const pfad = pfadVon(form.getAttribute("action") ?? "");
      const id = form.id && /^[\w-]+$/.test(form.id) ? `#${form.id}` : "";
      const name = form.getAttribute("name");
      push("submit", `form${id}${name ? `[name=${name}]` : ""}${pfad ? ` ${pfad}` : ""}`);
    } catch {
      // ignorieren
    }
  };
  document.addEventListener("click", onClick, true);
  document.addEventListener("submit", onSubmit, true);

  deinstallieren = () => {
    history.pushState = origPush;
    history.replaceState = origReplace;
    window.removeEventListener("popstate", route);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("submit", onSubmit, true);
  };
}

export function uninstallBreadcrumbs(): void {
  deinstallieren?.();
  deinstallieren = null;
}
