import type { StatusKey } from "../components/apple/status";
import type { Auftrag, AuftragStatus, Vorgang, VorgangStatus } from "../types";

/** Office-Links in die Detail-Panels: die Seiten lesen diese Query-Parameter
 * beim Laden (siehe OfficeProjektePage/OfficeAuftraegePage). */
export const projektLink = (id: string) => `/projekte?projekt=${id}`;
export const auftragLink = (id: string) => `/auftraege?auftrag=${id}`;

// Storniert zaehlt als erledigt: der Server rechnet vorgaenge_erledigt so (wie vorgaenge_gesamt), sonst
// wuerden Tabelle und Fortschrittsbalken verschiedene Zahlen zeigen und ein Auftrag nie "x / x" erreichen.
const ERLEDIGT: VorgangStatus[] = ["abgeschlossen", "abgerechnet", "storniert"];
const OFFEN_AUSGENOMMEN: VorgangStatus[] = ["abgeschlossen", "abgerechnet", "storniert"];

export const istVorgangErledigt = (status: VorgangStatus) => ERLEDIGT.includes(status);
export const istVorgangOffen = (status: VorgangStatus) => !OFFEN_AUSGENOMMEN.includes(status);

export function auftragStatusZuToken(status: AuftragStatus): StatusKey {
  return { offen: "neu", in_arbeit: "arbeit", abgeschlossen: "erledigt", storniert: "geplant" }[status] as StatusKey;
}

export interface ZuordnungsWahl {
  projektId: string;
  auftragId: string;
}

/** Auftragsliste im Auswahlfeld: nur Aufträge des gewählten Projekts, ohne Projekt alle. */
export function auftraegeFuerProjekt(auftraege: Auftrag[], projektId: string): Auftrag[] {
  return projektId ? auftraege.filter((a) => a.projekt_id === projektId) : auftraege;
}

/** Projekt gewechselt: ein Auftrag, der nicht zum neuen Projekt gehört, fällt weg. */
export function projektGewaehlt(auftraege: Auftrag[], alt: ZuordnungsWahl, projektId: string): ZuordnungsWahl {
  const auftrag = auftraege.find((a) => a.id === alt.auftragId);
  const passt = !!auftrag && (!projektId || auftrag.projekt_id === projektId);
  return { projektId, auftragId: passt ? alt.auftragId : "" };
}

/** Auftrag gewählt: dessen Projekt wird übernommen (Kette Projekt > Auftrag). */
export function auftragGewaehlt(auftraege: Auftrag[], alt: ZuordnungsWahl, auftragId: string): ZuordnungsWahl {
  if (!auftragId) return { ...alt, auftragId: "" };
  const auftrag = auftraege.find((a) => a.id === auftragId);
  return { projektId: auftrag?.projekt_id ?? "", auftragId };
}

export interface AuftragsGruppe {
  auftrag: Auftrag;
  vorgaenge: Vorgang[];
  erledigt: number;
}

/** Vorgänge eines Projekts je Auftrag; ohne Auftrag in `ohneAuftrag`. Aufträge ohne Vorgang
 * bleiben als leere Gruppe erhalten, Vorgänge mit unbekanntem Auftrag (z. B. fehlendes Recht) fallen
 * ebenfalls in `ohneAuftrag`, damit keiner in der Zählung verloren geht. */
export function gruppiereNachAuftrag(auftraege: Auftrag[], vorgaenge: Vorgang[]) {
  const bekannt = new Set(auftraege.map((a) => a.id));
  const gruppen: AuftragsGruppe[] = auftraege.map((auftrag) => {
    const eigene = vorgaenge.filter((v) => v.auftrag_id === auftrag.id);
    return { auftrag, vorgaenge: eigene, erledigt: eigene.filter((v) => istVorgangErledigt(v.status)).length };
  });
  const ohneAuftrag = vorgaenge.filter((v) => !v.auftrag_id || !bekannt.has(v.auftrag_id));
  return { gruppen, ohneAuftrag };
}
