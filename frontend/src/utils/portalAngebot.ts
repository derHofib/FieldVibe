const ZEITZONE = "Europe/Berlin";

/** Das Backend liefert das Fristende als exklusive Obergrenze (Beginn des
 * Folgetags in Betriebszeit). Angezeigt wird der letzte Tag, an dem noch
 * widerrufen werden kann. */
export function widerrufFristLetzterTag(fristBis: string): string {
  const letzteMinute = new Date(new Date(fristBis).getTime() - 60_000);
  return letzteMinute.toLocaleDateString("de-DE", { timeZone: ZEITZONE });
}

export function datumZeit(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { timeZone: ZEITZONE, dateStyle: "medium", timeStyle: "short" });
}

/** Absaetze einer Belehrung: Leerzeile trennt, einzelne Zeilenumbrueche
 * bleiben als Umbruch erhalten (white-space: pre-line beim Rendern). */
export function absaetze(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((a) => a.trim())
    .filter(Boolean);
}

/** Stoesst den Browser-Download einer Textdatei an (Muster-Widerrufsformular). */
export function ladeTextdatei(dateiname: string, inhalt: string): void {
  const url = URL.createObjectURL(new Blob([inhalt], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = dateiname;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
