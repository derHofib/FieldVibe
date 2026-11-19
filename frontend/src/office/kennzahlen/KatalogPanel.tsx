import { ClipboardList, Phone, Plus, Receipt, TrendingUp, type LucideIcon } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { SearchField } from "../../components/apple/SearchField";
import { SymbolKachel, type KachelFarbe } from "../../components/apple/SymbolKachel";
import type { KennzahlBereich, KennzahlDef } from "../../types/kennzahlen";

export const MAX_WIDGETS = 30;

export const BEREICHE: { schluessel: KennzahlBereich; label: string; icon: LucideIcon; farbe: KachelFarbe }[] = [
  { schluessel: "vorgaenge", label: "Vorgänge", icon: ClipboardList, farbe: "blue" },
  { schluessel: "finanzen", label: "Finanzen", icon: Receipt, farbe: "green" },
  { schluessel: "sales", label: "Sales", icon: TrendingUp, farbe: "indigo" },
  { schluessel: "telefonate", label: "Telefonate", icon: Phone, farbe: "orange" },
];

/** Rechte Spalte im Bearbeiten-Modus, im Raster neben den Widgets (kein Overlay: Das Dashboard bleibt sichtbar,
 * während man etwas hinzufügt). Gemeinsame Hülle für Katalog und Widget-Einstellungen. */
export function BearbeitenSpalte({ titel, kopf, children }: { titel: string; kopf?: ReactNode; children: ReactNode }) {
  return (
    <aside
      aria-label={titel}
      className="card-ap flex w-full flex-col overflow-hidden lg:sticky lg:top-5 lg:max-h-[calc(100vh-2.5rem)] lg:w-[380px] lg:shrink-0 lg:self-start"
    >
      {kopf ?? (
        <div className="border-b-[0.5px] border-sep px-4 py-3">
          <h2 className="text-zeile font-semibold text-label">{titel}</h2>
        </div>
      )}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  );
}

export function KatalogPanel({
  katalog,
  anzahlWidgets,
  onHinzufuegen,
}: {
  katalog: KennzahlDef[];
  anzahlWidgets: number;
  onHinzufuegen: (def: KennzahlDef) => void;
}) {
  const [suche, setSuche] = useState("");
  const voll = anzahlWidgets >= MAX_WIDGETS;

  const gruppen = useMemo(() => {
    const begriff = suche.trim().toLocaleLowerCase("de-DE");
    return BEREICHE.map((bereich) => ({
      ...bereich,
      eintraege: katalog.filter(
        (def) =>
          def.bereich === bereich.schluessel &&
          (begriff === "" || `${def.titel} ${def.beschreibung}`.toLocaleLowerCase("de-DE").includes(begriff)),
      ),
    })).filter((gruppe) => gruppe.eintraege.length > 0);
  }, [katalog, suche]);

  return (
    <BearbeitenSpalte titel="Kennzahl hinzufügen">
      <div className="space-y-3 px-4 py-3">
        <SearchField value={suche} onChange={setSuche} placeholder="Kennzahl suchen" ariaLabel="Kennzahl suchen" />
        {voll && (
          <p role="status" className="text-sekundaer text-label2">
            Mehr als {MAX_WIDGETS} Kennzahlen passen nicht in ein Dashboard.
          </p>
        )}
      </div>

      {gruppen.length === 0 && (
        <p className="px-4 pb-4 text-sekundaer text-label2">
          {suche.trim() ? "Keine passende Kennzahl gefunden." : "Keine Kennzahlen verfügbar."}
        </p>
      )}

      {gruppen.map((gruppe) => (
        <section key={gruppe.schluessel} aria-label={gruppe.label} className="pb-3">
          <h3 className="px-4 pt-1 pb-1.5 text-meta font-semibold tracking-wide text-label2 uppercase">{gruppe.label}</h3>
          <ul className="mx-3 divide-y-[0.5px] divide-sep rounded-[var(--radius-ap-md)] bg-cell">
            {gruppe.eintraege.map((def) => (
              <li key={def.schluessel} className="flex items-center gap-3 px-3 py-2.5">
                <SymbolKachel icon={gruppe.icon} farbe={gruppe.farbe} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-fliess font-semibold text-label">{def.titel}</p>
                  <p className="line-clamp-2 text-sekundaer text-label2">{def.beschreibung}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onHinzufuegen(def)}
                  disabled={voll}
                  aria-label={`${def.titel} hinzufügen`}
                  title="Hinzufügen"
                  className="btn-ap-toolbar shrink-0 disabled:opacity-40"
                >
                  <Plus size={16} strokeWidth={2} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </BearbeitenSpalte>
  );
}
