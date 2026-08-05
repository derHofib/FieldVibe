/** Analog zu openPdfBlob (utils/pdf.ts), aber fuer Dateien, die der Browser
 * nicht sinnvoll inline anzeigen kann (z.B. CSV) -- erzwingt stattdessen
 * einen Download unter dem gewuenschten Dateinamen. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
