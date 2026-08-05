/** Opens a PDF blob in a new tab. Revokes the object URL after a delay --
 * immediately would race the new tab's own load of it. */
export function openPdfBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
