/** Lesbare Fassung eines technischen Audit-Bezeichners ("rechnung_storniert" -> "Rechnung storniert",
 * "mandant.created" -> "Mandant · created"). Die Bezeichner sind offen (jede Route vergibt eigene),
 * deshalb keine feste Tabelle, sondern nur Satzzeichen und Großschreibung. */
export function auditLabel(bezeichner: string | null | undefined): string {
  if (!bezeichner) return "–";
  const text = bezeichner.replace(/_/g, " ").replace(/\./g, " · ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
