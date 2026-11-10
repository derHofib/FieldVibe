import type { Kunde, Material } from "../types";

// Von der Feld-Seite (GeschaeftPage) und den Office-Listen (office/kunden,
// office/material) gemeinsam genutzt, damit Suche und Unterbestand-Regel
// nicht auseinanderlaufen.

export function istUnterbestand(m: Material): boolean {
  return Number(m.bestand_gesamt) <= Number(m.mindestbestand);
}

export function filtereKunden(kunden: Kunde[], suche: string): Kunde[] {
  const q = suche.trim().toLowerCase();
  if (!q) return kunden;
  return kunden.filter(
    (k) => k.name.toLowerCase().includes(q) || (k.kundennummer ?? "").toLowerCase().includes(q),
  );
}

export interface MaterialFilter {
  lieferantId?: string;
  tagId?: string;
  nurUnterbestand?: boolean;
  suche?: string;
}

export function filtereMaterial(material: Material[], filter: MaterialFilter): Material[] {
  const q = (filter.suche ?? "").trim().toLowerCase();
  return material.filter((m) => {
    if (filter.lieferantId && m.lieferant_id !== filter.lieferantId) return false;
    if (filter.tagId && !m.tag_ids.includes(filter.tagId)) return false;
    if (filter.nurUnterbestand && !istUnterbestand(m)) return false;
    if (q && !(m.bezeichnung.toLowerCase().includes(q) || (m.artikelnummer ?? "").toLowerCase().includes(q))) {
      return false;
    }
    return true;
  });
}
