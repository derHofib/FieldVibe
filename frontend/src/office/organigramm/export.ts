import { besetzungText, POSITION_STATUS_LABEL } from "./darstellung";
import type { ListenZeile } from "./liste";

export const CSV_KOPF = [
  "Ebene",
  "Pfad",
  "Titel",
  "Typ",
  "Organisationseinheit",
  "Account-Typ",
  "Status",
  "Soll",
  "Ist",
  "Besetzung",
] as const;

/** Maskiert ein Feld fuer CSV (Semikolon-getrennt) und entschaerft Formel-Praefixe (Excel-Injection). */
export function csvFeld(wert: string | number | null | undefined): string {
  let text = wert === null || wert === undefined ? "" : String(wert);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[;"\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Kontextknoten (nur Pfad, ohne Details) werden nicht exportiert -- sie enthalten keine Daten. */
export function positionenCsv(zeilen: ListenZeile[]): string {
  const daten = zeilen
    .filter((z) => !z.position.kontext)
    .map((z) => {
      const p = z.position;
      return [
        z.tiefe + 1,
        z.pfad,
        p.titel,
        p.typ === "stabsstelle" ? "Stabsstelle" : "Linie",
        p.org_einheit?.name,
        p.account_typ?.name,
        p.status ? POSITION_STATUS_LABEL[p.status] : "",
        p.soll_besetzung ?? 0,
        p.ist_besetzung ?? 0,
        (p.besetzungen ?? []).length > 0 ? besetzungText(p) : "",
      ]
        .map(csvFeld)
        .join(";");
    });
  return [CSV_KOPF.map(csvFeld).join(";"), ...daten].join("\r\n");
}

export function csvDateiname(heute: Date = new Date()): string {
  return `organigramm-${heute.toISOString().slice(0, 10)}.csv`;
}

/** Download im Browser; BOM, damit Excel UTF-8 (Umlaute) erkennt. */
export function csvHerunterladen(inhalt: string, dateiname: string): void {
  const blob = new Blob(["\uFEFF", inhalt], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = dateiname;
  a.click();
  URL.revokeObjectURL(url);
}
