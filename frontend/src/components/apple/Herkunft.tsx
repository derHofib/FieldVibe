import { File, Folder } from "lucide-react";

/** Herkunft-Kennzeichnung (Abschnitt 3.3): Projekt immer Indigo + Ordner-
 * Symbol, Einzelauftrag --label2 + Dokument-Symbol. Farbe steht nie allein
 * -- immer mit Symbol + Text (Abschnitt 6). Kompakte Inline-Variante fuer
 * Listenzeilen/Karten; fuer die groessere Kachel-Darstellung (Inspektor/
 * Detailseite) siehe SymbolKachel mit farbe="indigo"/"gray". */
export function HerkunftZeile({
  projektName,
  gefuellt = false,
}: {
  projektName: string | null;
  /** Ordner-Symbol gefuellt (Mobil) statt Strich (Desktop), siehe Abschnitt 3.3. */
  gefuellt?: boolean;
}) {
  if (projektName) {
    return (
      <span className="inline-flex items-center gap-1 text-[13px] font-medium text-origin-projekt">
        <Folder size={13} strokeWidth={2} className={gefuellt ? "fill-current" : undefined} aria-hidden="true" />
        {projektName}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[13px] text-label2">
      <File size={13} strokeWidth={2} aria-hidden="true" />
      Einzelauftrag
    </span>
  );
}
