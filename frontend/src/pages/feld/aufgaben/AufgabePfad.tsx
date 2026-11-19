import { ChevronRight, Folder, Layers, Rss, type LucideIcon } from "lucide-react";

import type { ProjektAufgabe } from "../../../types";
import { auftragLink, projektLink } from "../../../utils/verknuepfung";
import { auftragIdVon, projektIdVon, projektNameVon, type PfadFelder } from "./aufgabenLogik";

type PfadAufgabe = PfadFelder & Pick<ProjektAufgabe, "vorgang_id" | "vorgang_vorgangsnummer" | "auftrag_titel">;

interface Glied {
  key: string;
  icon: LucideIcon;
  text: string;
  /** null = reiner Text. */
  ziel: string | null;
}

/** Glieder des Pfads Projekt > Auftrag > Vorgang. Projekt und Auftrag sind nur mit `linksAktiv` (Office mit Recht
 * projekte/sehen) Links; der Vorgang ist immer einer, denn auch Techniker haben die Vorgangsseite. */
export function pfadGlieder(a: PfadAufgabe, linksAktiv: boolean): Glied[] {
  const glieder: Glied[] = [];
  const projekt = projektNameVon(a);
  const projektId = projektIdVon(a);
  if (projekt) glieder.push({ key: "projekt", icon: Folder, text: projekt, ziel: linksAktiv && projektId ? projektLink(projektId) : null });
  const auftragId = auftragIdVon(a);
  if (a.auftrag_titel) glieder.push({ key: "auftrag", icon: Layers, text: a.auftrag_titel, ziel: linksAktiv && auftragId ? auftragLink(auftragId) : null });
  if (a.vorgang_id) glieder.push({ key: "vorgang", icon: Rss, text: a.vorgang_vorgangsnummer ?? "Vorgang", ziel: `/vorgaenge/${a.vorgang_id}` });
  return glieder;
}

/** "Gehört zu" einer Aufgabe als Kette mit Icons; `kurz` kürzt lange Namen (Karten in der Feld-App). */
export function AufgabePfad({
  aufgabe,
  linksAktiv,
  navigate,
  kurz = false,
  className = "",
}: {
  aufgabe: PfadAufgabe;
  linksAktiv: boolean;
  navigate: (to: string) => void;
  kurz?: boolean;
  className?: string;
}) {
  const glieder = pfadGlieder(aufgabe, linksAktiv);
  if (glieder.length === 0) return <span className={`text-label3 ${className}`}>–</span>;
  const textKlasse = kurz ? "max-w-[9rem] truncate" : "max-w-[16rem] truncate";

  return (
    <nav aria-label="Gehört zu" className={`flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5 text-sekundaer ${className}`}>
      {glieder.map((g, i) => {
        const Icon = g.icon;
        return (
          <span key={g.key} className="inline-flex min-w-0 items-center gap-1">
            {i > 0 && <ChevronRight size={12} strokeWidth={2} className="shrink-0 text-label3" aria-hidden="true" />}
            <Icon size={13} strokeWidth={1.5} className={`shrink-0 ${g.ziel ? "text-tint-text" : "text-label2"}`} aria-hidden="true" />
            {g.ziel ? (
              <button
                type="button"
                onClick={(e) => {
                  // Die Zeile bzw. Karte darum öffnet sonst zusätzlich das Detail.
                  e.stopPropagation();
                  navigate(g.ziel!);
                }}
                className={`${textKlasse} text-tint-text underline-offset-2 hover:underline`}
              >
                {g.text}
              </button>
            ) : (
              <span className={`${textKlasse} text-label2`}>{g.text}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
