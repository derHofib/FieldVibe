import type { KundeRefKurz } from "../types";
import type { SearchableSelectOption } from "../components/SearchableSelect";

/** Leerer Wert = Rechnung geht an den Auftraggeber selbst. */
export const RECHNUNG_AN_AUFTRAGGEBER = "";

/**
 * Auswahl für "Rechnung an": Auftraggeber, dann die von ihm verwalteten Kunden (z. B. WEGs einer
 * Hausverwaltung), dann alle übrigen Kunden. Der Auftraggeber selbst steht nur einmal oben.
 */
export function rechnungAnOptionen(
  auftraggeber: KundeRefKurz | null,
  verwaltete: KundeRefKurz[],
  alle: { id: string; name: string }[],
): SearchableSelectOption[] {
  const verwalteteIds = new Set(verwaltete.map((k) => k.id));
  const optionen: SearchableSelectOption[] = [
    { value: RECHNUNG_AN_AUFTRAGGEBER, label: auftraggeber ? `Auftraggeber (${auftraggeber.name})` : "Auftraggeber" },
  ];
  for (const k of verwaltete) {
    optionen.push({
      value: k.id,
      label: k.name,
      sublabel: auftraggeber ? `Verwaltet von ${auftraggeber.name}` : "Verwalteter Kunde",
    });
  }
  for (const k of alle) {
    if (k.id === auftraggeber?.id || verwalteteIds.has(k.id)) continue;
    optionen.push({ value: k.id, label: k.name });
  }
  return optionen;
}
