import { describe, expect, it } from "vitest";

import { ApiError } from "../../api/client";
import type { Position } from "../../types/organigramm";
import {
  besetzungText,
  istUnterbesetzt,
  knotenDarstellung,
  kontextAktionen,
  neuePositionBody,
  sollIst,
  verstaendlicherFehler,
} from "./darstellung";

const pos = (extra: Partial<Position> = {}): Position => ({
  id: "p1",
  parent_id: "wurzel",
  titel: "Teamleitung",
  typ: "linie",
  status: "besetzt",
  geplant: false,
  soll_besetzung: 1,
  ist_besetzung: 1,
  besetzungen: [{ id: "b1", user_id: "u1", name: "Anna Beispiel", art: "regulaer", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null }],
  ...extra,
});

describe("knotenDarstellung", () => {
  it("unterscheidet besetzt, vakant (gestrichelt), geplant (blass) und Kontext", () => {
    expect(knotenDarstellung(pos())).toMatchObject({ variante: "besetzt", gestrichelt: false, blass: false, statusLabel: "Besetzt" });
    expect(knotenDarstellung(pos({ status: "vakant" }))).toMatchObject({ variante: "vakant", gestrichelt: true, statusLabel: "Vakant" });
    expect(knotenDarstellung(pos({ status: "geplant" }))).toMatchObject({ variante: "geplant", blass: true, statusLabel: "Platzhalter" });
    expect(knotenDarstellung({ id: "k", parent_id: null, titel: "Pfad", typ: "linie", kontext: true })).toMatchObject({
      variante: "kontext",
      blass: true,
      statusLabel: null,
    });
  });

  it("markiert Stabsstellen unabhaengig vom Status", () => {
    expect(knotenDarstellung(pos({ typ: "stabsstelle", status: "vakant" }))).toMatchObject({ stab: true, variante: "vakant" });
    expect(knotenDarstellung(pos()).stab).toBe(false);
  });
});

describe("besetzungText / sollIst", () => {
  it("zeigt Namen, sonst vakant bzw. Platzhalter", () => {
    expect(besetzungText(pos())).toBe("Anna Beispiel");
    expect(besetzungText(pos({ status: "vakant", besetzungen: [], ist_besetzung: 0 }))).toBe("vakant");
    expect(besetzungText(pos({ status: "geplant", besetzungen: [], ist_besetzung: 0 }))).toBe("Platzhalter");
  });

  it("nennt ohne Namensrecht nur die Anzahl (DSGVO)", () => {
    const ohneNamen = pos({
      besetzungen: [
        { id: "b1", name: null, art: "regulaer", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null },
        { id: "b2", art: "vertretung", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null },
      ],
    });
    expect(besetzungText(ohneNamen)).toBe("2 Personen");
  });

  it("formatiert Soll/Ist und erkennt Unterbesetzung", () => {
    expect(sollIst(pos({ soll_besetzung: 3, ist_besetzung: 2 }))).toBe("2/3");
    expect(istUnterbesetzt(pos({ soll_besetzung: 3, ist_besetzung: 2 }))).toBe(true);
    expect(istUnterbesetzt(pos({ status: "geplant", geplant: true, soll_besetzung: 1, ist_besetzung: 0 }))).toBe(false);
  });
});

describe("kontextAktionen", () => {
  const darf = (...erlaubt: string[]) => (a: string) => erlaubt.includes(a);

  it("zeigt nur Details und 'Anzeigen als' ohne Schreibrechte", () => {
    expect(kontextAktionen(pos(), darf("sehen"), 0)).toEqual(["details", "anzeigen_als"]);
  });

  it("bietet Anlegen/Duplizieren nur mit erstellen an", () => {
    const a = kontextAktionen(pos(), darf("sehen", "erstellen"), 0);
    expect(a).toEqual(expect.arrayContaining(["darunter", "platzhalter", "stabsstelle", "duplizieren"]));
    expect(a).not.toContain("archivieren");
    expect(a).not.toContain("rechte");
  });

  it("bietet Rechte nur mit rechte_verwalten an", () => {
    expect(kontextAktionen(pos(), darf("rechte_verwalten"), 0)).toContain("rechte");
  });

  it("bietet Loeschen nur ohne Unterpositionen und ohne Besetzung an, Archivieren immer mit loeschen-Recht", () => {
    const frei = pos({ besetzungen: [], status: "vakant", ist_besetzung: 0 });
    expect(kontextAktionen(frei, darf("loeschen"), 0)).toEqual(expect.arrayContaining(["archivieren", "loeschen"]));
    expect(kontextAktionen(frei, darf("loeschen"), 2)).not.toContain("loeschen");
    expect(kontextAktionen(frei, darf("loeschen"), 2)).toContain("archivieren");
    expect(kontextAktionen(pos(), darf("loeschen"), 0)).not.toContain("loeschen");
  });

  it("schliesst bei der Wurzel Duplizieren, Archivieren und Loeschen aus", () => {
    const wurzel = pos({ parent_id: null, besetzungen: [], status: "vakant" });
    const a = kontextAktionen(wurzel, darf("erstellen", "loeschen"), 0);
    expect(a).not.toContain("duplizieren");
    expect(a).not.toContain("archivieren");
    expect(a).not.toContain("loeschen");
    expect(a).toContain("darunter");
  });

  it("bietet bei Kontextknoten und archivierten Positionen nichts bzw. nur Details an", () => {
    expect(kontextAktionen({ id: "k", parent_id: null, titel: "x", typ: "linie", kontext: true }, darf("erstellen"), 0)).toEqual([]);
    expect(kontextAktionen(pos({ archiviert_am: "2026-01-01T00:00:00Z" }), darf("erstellen", "loeschen"), 0)).toEqual(["details"]);
  });
});

describe("verstaendlicherFehler", () => {
  it("ordnet 403 als Eskalationsschutz ein und behaelt die Backend-Meldung", () => {
    const text = verstaendlicherFehler(new ApiError(403, "Zum Vergeben von Rechten ist das Recht „Rechte verwalten“ erforderlich"));
    expect(text).toContain("Eskalationsschutz");
    expect(text).toContain("Rechte verwalten");
  });

  it("macht aus 409 eine 'Nicht möglich'-Meldung", () => {
    expect(verstaendlicherFehler(new ApiError(409, "Zyklus"))).toBe("Nicht möglich: Zyklus");
  });

  it("faellt bei unbekannten Fehlern auf den Fallback zurueck", () => {
    expect(verstaendlicherFehler("kaputt", "Speichern fehlgeschlagen")).toBe("Speichern fehlgeschlagen");
  });
});

describe("neuePositionBody", () => {
  it("setzt typ/geplant je Menueeintrag und laesst leere Auswahlen weg", () => {
    expect(neuePositionBody("darunter", "p", { titel: " Montage " })).toEqual({
      parent_id: "p",
      typ: "linie",
      titel: "Montage",
      geplant: false,
      soll_besetzung: 1,
    });
    expect(neuePositionBody("platzhalter", "p", { titel: "x", orgEinheitId: "e", accountTypId: "t", sollBesetzung: 2 })).toMatchObject({
      geplant: true,
      typ: "linie",
      org_einheit_id: "e",
      account_typ_id: "t",
      soll_besetzung: 2,
    });
    expect(neuePositionBody("stabsstelle", "p", { titel: "QM" })).toMatchObject({ typ: "stabsstelle", geplant: false });
  });
});
