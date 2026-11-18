import type { FormField, FormGroup } from "../../types";

/** Platzhalterwerte für die Vorschau, wenn es noch kein ausgefülltes Protokoll
 * der Vorlage gibt. Zahlen liegen bewusst innerhalb eines gesetzten Grenzwerts,
 * damit die Vorschau nicht schon "Fehler" zeigt. */
export function beispielWert(feld: FormField): unknown {
  const werte = Array.isArray(feld.optionen.werte) ? (feld.optionen.werte as string[]) : [];
  switch (feld.feld_typ) {
    case "text":
    case "textarea":
      return "Beispieltext";
    case "zahl": {
      const max = typeof feld.validation.warn_max === "number" ? feld.validation.warn_max : null;
      const min = typeof feld.validation.warn_min === "number" ? feld.validation.warn_min : null;
      if (max !== null && min !== null) return Math.round((min + max) / 2);
      if (max !== null) return Math.max(0, Math.floor(max / 2));
      return min !== null ? min + 1 : 12;
    }
    case "betrag":
      return 120;
    case "datum":
      return new Date().toISOString().slice(0, 10);
    case "dropdown":
      return werte[0] ?? "Auswahl";
    case "mehrfachauswahl":
      return werte.slice(0, 2);
    case "ja_nein":
      return true;
    case "bewertung":
      return Number(feld.optionen.max ?? 5);
    case "email":
      return "beispiel@firma.de";
    case "telefon":
      return "0123 456789";
    case "adresse":
      return { strasse: "Musterweg 3", plz: "12345", ort: "Musterstadt" };
    default:
      return undefined;
  }
}

export function beispielWerte(felder: FormField[], gruppen: FormGroup[]): Record<string, unknown> {
  const werte: Record<string, unknown> = {};
  for (const f of felder.filter((x) => x.group_key === null)) {
    const w = beispielWert(f);
    if (w !== undefined) werte[f.key] = w;
  }
  for (const g of gruppen) {
    const zeile: Record<string, unknown> = {};
    for (const f of felder.filter((x) => x.group_key === g.key)) {
      const w = beispielWert(f);
      if (w !== undefined) zeile[f.key] = w;
    }
    werte[g.key] = [zeile];
  }
  return werte;
}
