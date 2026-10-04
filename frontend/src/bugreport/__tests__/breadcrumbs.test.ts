// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { installBreadcrumbs, uninstallBreadcrumbs } from "../breadcrumbs";
import { Ringpuffer } from "../ringpuffer";
import type { Breadcrumb } from "../typen";

let puffer: Ringpuffer<Breadcrumb>;

beforeEach(() => {
  puffer = new Ringpuffer<Breadcrumb>(100);
  installBreadcrumbs({ puffer });
});

afterEach(() => {
  uninstallBreadcrumbs();
  document.body.innerHTML = "";
});

describe("Breadcrumbs", () => {
  it("erfasst Klick auf Button mit Selektor und Text", () => {
    document.body.innerHTML = `<button id="speichern" class="btn primary extra">Speichern</button>`;
    document.getElementById("speichern")!.click();
    expect(puffer.toArray()[0]).toMatchObject({ typ: "klick", ziel: "button#speichern.btn.primary", text: "Speichern" });
  });

  it("nimmt bei Klick auf ein Kind den naechsten Button", () => {
    document.body.innerHTML = `<button id="b"><span>Neu anlegen</span></button>`;
    document.querySelector("span")!.click();
    expect(puffer.toArray()[0]).toMatchObject({ ziel: "button#b", text: "Neu anlegen" });
  });

  it("erfasst bei Input weder Wert noch Text", () => {
    document.body.innerHTML = `<input type="password" name="pw" value="supergeheim"><textarea name="t">privat</textarea>`;
    (document.querySelector("input") as HTMLInputElement).click();
    (document.querySelector("textarea") as HTMLTextAreaElement).click();
    const [a, b] = puffer.toArray();
    expect(a).toEqual({ zeit: a.zeit, typ: "klick", ziel: "input[type=password][name=pw]" });
    expect(b.ziel).toBe("textarea[name=t]");
    expect(JSON.stringify(puffer.toArray())).not.toMatch(/supergeheim|privat/);
  });

  it("erfasst keinen Text von Containern mit Eingabefeldern (select-Optionen)", () => {
    document.body.innerHTML = `<label id="l">Land <select name="land"><option>Geheimland</option></select></label>`;
    document.getElementById("l")!.click();
    const e = puffer.toArray()[0];
    expect(e.text).toBeUndefined();
    expect(JSON.stringify(e)).not.toContain("Geheimland");
  });

  it("kuerzt Text auf 80 Zeichen und maskiert E-Mails", () => {
    document.body.innerHTML = `<a id="a" href="#">${"x".repeat(200)}</a><button id="m">anna@example.com</button>`;
    document.getElementById("a")!.click();
    document.getElementById("m")!.click();
    const [a, m] = puffer.toArray();
    expect(a.text!.length).toBe(80);
    expect(m.text).toBe("[email]");
  });

  it("erfasst pushState/replaceState als Route ohne Query", () => {
    history.pushState({}, "", "/vorgaenge/5?token=abc");
    history.replaceState({}, "", "/kunden");
    expect(puffer.toArray().map((b) => [b.typ, b.ziel])).toEqual([
      ["route", "/vorgaenge/5"],
      ["route", "/kunden"],
    ]);
  });

  it("erfasst Formular-Submits nur mit id/name/action-Pfad", () => {
    document.body.innerHTML = `<form id="login" name="f" action="/api/login?x=1"><input name="passwort" value="geheim"></form>`;
    document.getElementById("login")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    const e = puffer.toArray()[0];
    expect(e).toMatchObject({ typ: "submit", ziel: "form#login[name=f] /api/login" });
    expect(JSON.stringify(e)).not.toContain("geheim");
  });

  it("stellt history beim uninstall wieder her", () => {
    uninstallBreadcrumbs();
    const vorher = puffer.laenge;
    history.pushState({}, "", "/egal");
    expect(puffer.laenge).toBe(vorher);
  });
});
