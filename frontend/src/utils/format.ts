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

// Lokaler Kalendertag als YYYY-MM-DD. toISOString() wuerde in UTC rechnen und
// zwischen 0 und 1/2 Uhr Ortszeit den Vortag liefern.
export function lokalesDatum(datum: Date): string {
  const monat = String(datum.getMonth() + 1).padStart(2, "0");
  const tag = String(datum.getDate()).padStart(2, "0");
  return `${datum.getFullYear()}-${monat}-${tag}`;
}

// Fuer Filterleisten: heutiges Datum (oder +offsetTage) als YYYY-MM-DD,
// wie es <input type="date"> und die Backend-Query-Parameter erwarten.
export function heuteIso(offsetTage = 0): string {
  const datum = new Date();
  datum.setDate(datum.getDate() + offsetTage);
  return lokalesDatum(datum);
}
