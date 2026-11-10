// Kleine Format-Helfer fuer Geldbetraege/Datum -- ersetzt das ueberall
// inline stehende `${x} EUR` und `new Date(x).toLocaleDateString("de-DE")`.

export function formatEuro(wert: string | number): string {
  const zahl = typeof wert === "string" ? Number(wert) : wert;
  if (Number.isNaN(zahl)) return `${wert} €`;
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(zahl);
}

export function formatDatum(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("de-DE");
}

// Lokaler Kalendertag als YYYY-MM-DD. toISOString() rechnet nach UTC um und
// liefert nachts in Deutschland (00:00-02:00) noch den Vortag.
export function datumZuIso(datum: Date): string {
  const monat = String(datum.getMonth() + 1).padStart(2, "0");
  const tag = String(datum.getDate()).padStart(2, "0");
  return `${datum.getFullYear()}-${monat}-${tag}`;
}

// Fuer Filterleisten: heutiges Datum (oder +offsetTage) als YYYY-MM-DD in
// Lokalzeit, wie es <input type="date"> und die Backend-Query-Parameter
// erwarten.
export function heuteIso(offsetTage = 0): string {
  const datum = new Date();
  datum.setDate(datum.getDate() + offsetTage);
  return datumZuIso(datum);
}

// Kalendertage von `vonIso` bis `bisIso` (negativ, wenn bis davor liegt). Rechnet
// auf UTC-Mitternacht der reinen Datumsteile, damit Sommerzeitwechsel keine
// 23-/25-Stunden-Tage in die Differenz bringen.
export function tageZwischen(vonIso: string, bisIso: string): number {
  const [vj, vm, vt] = vonIso.split("-").map(Number);
  const [bj, bm, bt] = bisIso.split("-").map(Number);
  return Math.round((Date.UTC(bj, bm - 1, bt) - Date.UTC(vj, vm - 1, vt)) / 86_400_000);
}

// "2026-10-19" -> "19.10.2026" ohne Date-Umweg (new Date("YYYY-MM-DD") ist UTC
// und kann je nach Zeitzone auf den Vortag fallen).
export function formatIsoTag(iso: string): string {
  const [j, m, t] = iso.split("-");
  return `${t}.${m}.${j}`;
}
